"""AI Analiz — günlük piyasa değerlendirme raporu.

Günün BİST, emtia, döviz/küresel, kripto ve TEFAS fon verileriyle öne çıkan
haber başlıklarını toplar ve:
  - ANTHROPIC_API_KEY tanımlıysa Claude (Anthropic) ile analist yorumu üretir
    (yapılandırılmış JSON çıktı),
  - anahtar yoksa aynı veriden kural bazlı bir rapor kurar.

Rapor günlük cache'lenir (backend/ai_report_cache.json) ve gün değişince ya da
zamanlayıcı ile her gün settings.ai_report_hour'da (varsayılan 10:00) yenilenir.
Yatırım tavsiyesi değildir; veri + dengeli yorumdur.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.services import market, news, overview

_CACHE_FILE = BACKEND_DIR / "ai_report_cache.json"
_mem_cache: dict | None = None

_SENTIMENTS = ["pozitif", "negatif", "karışık", "nötr"]

_NUM = {
    "type": "object",
    "properties": {
        "etiket": {"type": "string"},
        "deger": {"type": "string"},
        "degisim": {"type": "string"},
        "hava": {"type": "string", "enum": _SENTIMENTS},
    },
    "required": ["etiket", "deger", "degisim", "hava"],
    "additionalProperties": False,
}
_BOLUM = {
    "type": "object",
    "properties": {
        "baslik": {"type": "string"},
        "yorum": {"type": "string"},
        "hava": {"type": "string", "enum": _SENTIMENTS},
        "one_cikanlar": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["baslik", "yorum", "hava", "one_cikanlar"],
    "additionalProperties": False,
}
_HABER = {
    "type": "object",
    "properties": {"baslik": {"type": "string"}, "etki": {"type": "string"}},
    "required": ["baslik", "etki"],
    "additionalProperties": False,
}
_SCHEMA = {
    "type": "object",
    "properties": {
        "ozet": {"type": "string"},
        "genel_hava": {"type": "string", "enum": _SENTIMENTS},
        "gunun_rakamlari": {"type": "array", "items": _NUM},
        "bolumler": {"type": "array", "items": _BOLUM},
        "temalar": {"type": "array", "items": {"type": "string"}},
        "one_cikan_haberler": {"type": "array", "items": _HABER},
        "riskler": {"type": "array", "items": {"type": "string"}},
        "firsatlar": {"type": "array", "items": {"type": "string"}},
        "beklenti": {"type": "string"},
        "kapanis": {"type": "string"},
    },
    "required": [
        "ozet", "genel_hava", "gunun_rakamlari", "bolumler", "temalar",
        "one_cikan_haberler", "riskler", "firsatlar", "beklenti", "kapanis",
    ],
    "additionalProperties": False,
}

_SYSTEM = (
    "Sen deneyimli, tarafsız bir Türk piyasa analistisin. Sana günün BİST, emtia, "
    "döviz, küresel borsa, kripto ve TEFAS fon verileriyle öne çıkan haber başlıkları "
    "verilecek. Bunları sentezleyip Türkçe, AYRINTILI ve DERİNLEMESİNE bir GÜNLÜK "
    "PİYASA DEĞERLENDİRME raporu üret. Piyasa yorumcularının bakış açısını, verileri ve "
    "kendi dengeli yorumunu harmanla.\n"
    "Beklentiler:\n"
    "- ozet: 3-5 cümlelik güçlü bir genel bakış.\n"
    "- gunun_rakamlari: en önemli 6-10 değeri (BİST 100/30, Dolar, Euro, gram altın/"
    "gümüş, Brent, Bitcoin vb.) etiket/değer/değişim ile tablo halinde ver.\n"
    "- bolumler: EN AZ BİST, Emtia, Döviz & Küresel, Kripto, Fonlar başlıkları. Her "
    "bölümün 'yorum' alanı 3-5 cümle DOLU ve nedensellik içeren bir analiz olsun; "
    "'one_cikanlar' alanına o bölümün 3-6 somut maddesini (hisse/kod + rakam) koy.\n"
    "- temalar: günün öne çıkan 3-5 makro/piyasa temasını (ör. altında yön, risk "
    "iştahı, TL, kriptoda ayrışma) kısa maddelerle özetle.\n"
    "- one_cikan_haberler: en önemli 4-6 başlık; her biri için 'etki' alanına neden "
    "önemli olduğunu tek cümleyle yaz.\n"
    "- riskler ve firsatlar: dengeli biçimde, gözleme dayalı 2-5'er madde.\n"
    "- beklenti: kısa vadede izlenecek seviyeler/olaylar (2-4 cümle).\n"
    "- kapanis: genel değerlendirme ve dengeli kapanış yorumu.\n"
    "Kurallar: yalnızca verilen verilere ve genel piyasa bağlamına dayan, uydurma "
    "rakam/isim ekleme; BİREYSEL YATIRIM TAVSİYESİ VERME (al/sat deme), 'izlenebilir/"
    "takip edilebilir' gibi gözlem dili kullan; abartıdan kaçın; sayıları verideki gibi "
    "aktar. Çıktı zengin ve okunması keyifli olsun ama boş laf ve tekrar içermesin."
)


# ---------- yardımcılar ----------
def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"%{v * 100:+.2f}".replace(".", ",")


def _sign(v: float | None) -> str:
    if v is None:
        return "nötr"
    return "pozitif" if v > 0.0005 else "negatif" if v < -0.0005 else "nötr"


def _today() -> str:
    return datetime.now().date().isoformat()


# ---------- veri toplama ----------
def _collect(db: Session) -> dict:
    def safe(fn, default):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return default

    snap = safe(market.snapshot, [])
    metals = safe(market.precious_metals, {"metals": [], "usdtry": None})
    world = safe(lambda: market.market_board("world"), {"items": []})
    crypto_board = safe(lambda: market.market_board("crypto"), {"items": []})
    bist = safe(market.bist_movers, {"gainers": [], "losers": [], "most_traded": []})
    crypto = safe(market.crypto_movers, {"gainers": [], "losers": [], "most_traded": []})
    try:
        fon_g, fon_l, fon_asof = overview.top_fund_movers(db, kind="FON", limit=8)
    except Exception:  # noqa: BLE001
        fon_g, fon_l, fon_asof = [], [], None
    topics = {}
    for t in ("bist", "metals", "crypto", "world", "general"):
        topics[t] = safe(lambda t=t: news.news_for(t, 6), [])

    return {
        "snap": snap, "metals": metals, "world": world, "crypto_board": crypto_board,
        "bist": bist, "crypto": crypto,
        "fon_gainers": fon_g, "fon_losers": fon_l,
        "fon_asof": fon_asof.isoformat() if fon_asof else None,
        "news": topics,
    }


def _brief_text(d: dict) -> str:
    """LLM'e verilecek kompakt veri özeti."""
    lines: list[str] = [f"TARİH: {_today()}", ""]

    lines.append("PİYASA ŞERİDİ:")
    for m in d["snap"]:
        lines.append(f"  - {m['label']}: {m['value']:.2f} ({_pct(m.get('change'))})")

    lines.append("\nEMTİA (USD birim başına, günlük USD değişim):")
    for m in d["metals"].get("metals", []):
        lines.append(f"  - {m['name']} ({m['unit']}): {m['usd_price']:.2f} ({_pct(m.get('usd_change'))})")
    if d["metals"].get("usdtry"):
        lines.append(f"  (USD/TRY: {d['metals']['usdtry']:.2f})")

    lines.append("\nKÜRESEL BORSALAR/ENDEKSLER:")
    for it in d["world"].get("items", []):
        lines.append(f"  - {it['label']}: {it['value']:.2f} ({_pct(it.get('change'))})")

    def movers(title, m):
        lines.append(f"\n{title}:")
        g = ", ".join(f"{x['code']} {_pct(x['change'])}" for x in m.get("gainers", [])[:6])
        loss = ", ".join(f"{x['code']} {_pct(x['change'])}" for x in m.get("losers", [])[:6])
        tr = ", ".join(x["code"] for x in m.get("most_traded", [])[:6])
        lines.append(f"  En çok yükselen: {g or '—'}")
        lines.append(f"  En çok düşen: {loss or '—'}")
        lines.append(f"  En çok işlem gören: {tr or '—'}")

    movers("BİST HİSSELERİ (~40 likit hisse taraması)", d["bist"])

    lines.append("\nKRİPTO (USD):")
    for it in d["crypto_board"].get("items", [])[:6]:
        lines.append(f"  - {it['label']}: {it['value']:.2f} ({_pct(it.get('change'))})")
    movers("KRİPTO (CoinGecko top-100)", d["crypto"])

    lines.append("\nTEFAS FONLARI (günlük):")
    g = ", ".join(f"{x['code']} {_pct(x['change'])}" for x in d["fon_gainers"][:6])
    losf = ", ".join(f"{x['code']} {_pct(x['change'])}" for x in d["fon_losers"][:6])
    lines.append(f"  En çok kazandıran: {g or '—'}")
    lines.append(f"  En çok kaybettiren: {losf or '—'}")

    lines.append("\nÖNE ÇIKAN HABER BAŞLIKLARI:")
    seen = set()
    for topic, items in d["news"].items():
        for n in items[:4]:
            t = (n.get("title") or "").strip()
            if t and t not in seen:
                seen.add(t)
                lines.append(f"  - [{topic}] {t}")

    lines.append(
        "\nGörev: Yukarıdaki günün verileriyle şemaya uygun, AYRINTILI bir günlük "
        "değerlendirme raporu üret. gunun_rakamlari'nı en önemli değerlerle doldur; "
        "bolumler en az BİST, Emtia, Döviz & Küresel, Kripto ve Fonlar başlıklarını "
        "içersin ve her birinin yorumu 3-5 cümle olsun; temalar, riskler, firsatlar ve "
        "beklenti alanlarını da doldur. Rakam ve kodları verideki gibi kullan."
    )
    return "\n".join(lines)


# ---------- LLM raporu ----------
def _llm_report(brief: str) -> dict:
    import anthropic  # yalnızca anahtar varken gerekli

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.ai_model,
        max_tokens=12000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": _SCHEMA}},
        system=_SYSTEM,
        messages=[{"role": "user", "content": brief}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise RuntimeError("boş yanıt")
    data = json.loads(text)
    data["mode"] = "ai"
    data["model"] = settings.ai_model
    return data


# ---------- kural bazlı rapor (anahtar yoksa) ----------
def _find(items, label):
    for m in items:
        if m.get("label") == label:
            return m
    return None


def _rule_report(d: dict) -> dict:
    snap = d["snap"]
    bist100 = _find(snap, "BİST 100")
    bist30 = _find(snap, "BİST 30")
    dolar = _find(snap, "Dolar")
    euro = _find(snap, "Euro")
    gram = _find(snap, "Gram Altın")
    gumus = _find(snap, "Gram Gümüş")
    metals = {m["key"]: m for m in d["metals"].get("metals", [])}
    brent = metals.get("brent")
    btc = _find(d["crypto_board"].get("items", []), "Bitcoin")
    eth = _find(d["crypto_board"].get("items", []), "Ethereum")

    world_items = [i for i in d["world"].get("items", []) if i.get("change") is not None]
    w_up = sum(1 for i in world_items if i["change"] > 0)
    w_down = sum(1 for i in world_items if i["change"] < 0)
    w_best = max(world_items, key=lambda i: i["change"], default=None)
    w_worst = min(world_items, key=lambda i: i["change"], default=None)

    bg, bl, bt = d["bist"].get("gainers", []), d["bist"].get("losers", []), d["bist"].get("most_traded", [])
    cg, cl = d["crypto"].get("gainers", []), d["crypto"].get("losers", [])
    fg, fl = d["fon_gainers"], d["fon_losers"]

    def _num(label, m, fmt="{:.2f}"):
        if not m:
            return None
        return {"etiket": label, "deger": fmt.format(m["value"]),
                "degisim": _pct(m.get("change")), "hava": _sign(m.get("change"))}

    rakamlar = [x for x in [
        _num("BİST 100", bist100, "{:.0f}"), _num("BİST 30", bist30, "{:.0f}"),
        _num("Dolar/TL", dolar), _num("Euro/TL", euro),
        _num("Gram Altın", gram, "{:.0f}₺"), _num("Gram Gümüş", gumus, "{:.1f}₺"),
    ] if x]
    if brent:
        rakamlar.append({"etiket": "Brent Petrol", "deger": f"{brent['usd_price']:.1f}$",
                         "degisim": _pct(brent.get("usd_change")), "hava": _sign(brent.get("usd_change"))})
    if btc:
        rakamlar.append({"etiket": "Bitcoin", "deger": f"{btc['value']:,.0f}$",
                         "degisim": _pct(btc.get("change")), "hava": _sign(btc.get("change"))})

    def _rows(arr, n=4):
        return [f"{x['code']} {_pct(x['change'])}" for x in arr[:n]]

    bolumler = []

    by = ""
    if bist100:
        by += f"BİST 100 endeksi günü {_pct(bist100.get('change'))} değişimle {bist100['value']:.0f} seviyesinde geçiriyor. "
    if bist30 and bist30.get("change") is not None:
        by += f"BİST 30'da değişim {_pct(bist30.get('change'))}. "
    if bg:
        by += f"Yükselenlerde {bg[0]['code']} ({_pct(bg[0].get('change'))}) öne çıkıyor; "
    if bl:
        by += f"düşenlerde {bl[0]['code']} ({_pct(bl[0].get('change'))}) dikkat çekiyor. "
    if bt:
        by += f"İşlem hacminde {bt[0]['code']} başı çekiyor."
    bo = []
    if bg:
        bo.append("Yükselen: " + ", ".join(_rows(bg)))
    if bl:
        bo.append("Düşen: " + ", ".join(_rows(bl)))
    if bt:
        bo.append("İşlem gören: " + ", ".join(x["code"] for x in bt[:5]))
    bolumler.append({"baslik": "BİST", "yorum": by.strip() or "Veri sınırlı.",
                     "hava": _sign(bist100.get("change") if bist100 else None), "one_cikanlar": bo})

    ey = ""
    if gram:
        ey += f"Gram altın {gram['value']:.0f}₺ ile günü {_pct(gram.get('change'))} değişimle sürdürüyor. "
    if gumus:
        ey += f"Gram gümüş {_pct(gumus.get('change'))}. "
    if brent:
        ey += f"Enerji tarafında Brent petrol {brent['usd_price']:.1f}$ ({_pct(brent.get('usd_change'))}). "
    ey += "Değerli metaller ve emtia; dolar ile reel faiz beklentilerine duyarlı seyrediyor."
    eo = [f"{m['name']}: {m['usd_price']:.2f}$ ({_pct(m.get('usd_change'))})" for m in d["metals"].get("metals", [])[:6]]
    bolumler.append({"baslik": "Emtia", "yorum": ey.strip(),
                     "hava": _sign(gram.get("change") if gram else None), "one_cikanlar": eo})

    dy = ""
    if dolar:
        dy += f"Dolar/TL {dolar['value']:.2f} ({_pct(dolar.get('change'))}), "
    if euro:
        dy += f"Euro/TL {euro['value']:.2f} ({_pct(euro.get('change'))}). "
    dy += f"Küresel borsalarda {w_up} kalem yükseldi, {w_down} kalem geriledi. "
    if w_best:
        dy += f"En güçlü {w_best['label']} ({_pct(w_best['change'])}), "
    if w_worst:
        dy += f"en zayıf {w_worst['label']} ({_pct(w_worst['change'])})."
    do = [f"{i['label']}: {_pct(i['change'])}" for i in world_items[:6]]
    bolumler.append({"baslik": "Döviz & Küresel", "yorum": dy.strip(),
                     "hava": "pozitif" if w_up > w_down else "negatif" if w_down > w_up else "karışık",
                     "one_cikanlar": do})

    cy = ""
    if btc:
        cy += f"Bitcoin {btc['value']:,.0f}$ ({_pct(btc.get('change'))}). "
    if eth:
        cy += f"Ethereum {eth['value']:,.0f}$ ({_pct(eth.get('change'))}). "
    if cg:
        cy += f"Günün en çok yükseleni {cg[0]['code']} ({_pct(cg[0].get('change'))}), "
    if cl:
        cy += f"en çok düşeni {cl[0]['code']} ({_pct(cl[0].get('change'))}). "
    cy += "Kripto tarafında oynaklık yüksek; küçük ölçekli coinlerde sert ayrışmalar görülebiliyor."
    co = []
    if cg:
        co.append("Yükselen: " + ", ".join(_rows(cg)))
    if cl:
        co.append("Düşen: " + ", ".join(_rows(cl)))
    bolumler.append({"baslik": "Kripto", "yorum": cy.strip(),
                     "hava": _sign(btc.get("change") if btc else None), "one_cikanlar": co})

    fy = ""
    if fg:
        fy += f"TEFAS'ta günün en çok kazandıran fonu {fg[0]['code']} ({_pct(fg[0].get('change'))}). "
    if fl:
        fy += f"En çok kaybettiren {fl[0]['code']} ({_pct(fl[0].get('change'))}). "
    fy += "Fon getirileri; içerdikleri hisse/emtia/döviz ağırlığına göre günün piyasa yönünü yansıtıyor."
    fo = []
    if fg:
        fo.append("Kazandıran: " + ", ".join(_rows(fg)))
    if fl:
        fo.append("Kaybettiren: " + ", ".join(_rows(fl)))
    bolumler.append({"baslik": "Fonlar", "yorum": fy.strip(),
                     "hava": _sign(fg[0].get("change") if fg else None), "one_cikanlar": fo})

    temalar = []
    if gram and abs(gram.get("change") or 0) >= 0.005:
        temalar.append(f"Altın gram bazında {'güçlü' if gram['change'] > 0 else 'zayıf'} ({_pct(gram['change'])}).")
    if dolar:
        temalar.append(
            f"TL tarafında dolar {_pct(dolar.get('change'))} — "
            f"{'baskı sürüyor' if (dolar.get('change') or 0) > 0 else 'görece yatay'}."
        )
    temalar.append(
        f"Küresel risk iştahı {'alıcılı' if w_up > w_down else 'satıcılı' if w_down > w_up else 'kararsız'} "
        f"({w_up}↑/{w_down}↓)."
    )
    if btc:
        temalar.append(f"Kriptoda Bitcoin {_pct(btc.get('change'))}; piyasa {'iştahlı' if (btc.get('change') or 0) > 0 else 'temkinli'}.")
    if bg and bl:
        temalar.append(f"BİST'te ayrışma: {bg[0]['code']} önde, {bl[0]['code']} geride.")

    haberler = []
    seen = set()
    for topic in ("bist", "general", "metals", "crypto", "world"):
        for n in d["news"].get(topic, [])[:2]:
            t = (n.get("title") or "").strip()
            if t and t not in seen:
                seen.add(t)
                haberler.append({"baslik": t, "etki": n.get("source") or topic})
        if len(haberler) >= 6:
            break

    riskler, firsatlar = [], []
    for m in d["metals"].get("metals", []):
        ch = m.get("usd_change") or 0
        if ch <= -0.02:
            riskler.append(f"{m['name']} sert geriledi ({_pct(m['usd_change'])}); emtia tarafında baskı.")
        elif ch >= 0.02:
            firsatlar.append(f"{m['name']} güçlü ({_pct(m['usd_change'])}); ilgili varlıklar takip edilebilir.")
    if bl and (bl[0].get("change") or 0) <= -0.03:
        riskler.append(f"{bl[0]['code']} BİST'te belirgin düşüş ({_pct(bl[0]['change'])}).")
    if bg and (bg[0].get("change") or 0) >= 0.03:
        firsatlar.append(f"{bg[0]['code']} güçlü alıcılı ({_pct(bg[0]['change'])}); momentum izlenebilir.")
    vix = _find(d["world"].get("items", []), "VIX (Korku Endeksi)")
    if vix and vix.get("value", 0) and vix["value"] >= 20:
        riskler.append(f"VIX korku endeksi yüksek ({vix['value']:.1f}); oynaklık riski.")
    if w_down > w_up:
        riskler.append("Küresel borsalarda genele yayılan satış baskısı var.")
    else:
        firsatlar.append("Küresel risk iştahı görece canlı; hisse tarafı destekli.")
    if not riskler:
        riskler.append("Belirgin bir uç risk sinyali öne çıkmıyor; oynaklık normal aralıkta.")
    if not firsatlar:
        firsatlar.append("Net bir fırsat sinyali sınırlı; seçici ve temkinli seyir uygun.")

    signs = [b["hava"] for b in bolumler]
    pos, neg = signs.count("pozitif"), signs.count("negatif")
    genel = "pozitif" if pos > neg else "negatif" if neg > pos else "karışık"

    izle = []
    if bist100:
        izle.append(f"BİST 100 {bist100['value']:.0f}")
    if dolar:
        izle.append(f"Dolar/TL {dolar['value']:.2f}")
    if gram:
        izle.append(f"gram altın {gram['value']:.0f}₺")
    beklenti = (
        "Kısa vadede izlenecek başlıklar: " + (", ".join(izle) or "ana endeks ve kur seviyeleri") + ". "
        + ("Alıcılı hava korunursa yükseliş denemeleri sürebilir. " if genel == "pozitif"
           else "Satış baskısı sürerse geri çekilmeler derinleşebilir. " if genel == "negatif"
           else "Yönsüz seyirde seviyelerin korunması önemli olacak. ")
        + "Küresel veri akışı, dolar ve emtia fiyatları belirleyici."
    )

    ozet_parts = []
    if bist100:
        ozet_parts.append(f"BİST 100 {bist100['value']:.0f} ({_pct(bist100.get('change'))})")
    if dolar:
        ozet_parts.append(f"Dolar/TL {dolar['value']:.2f}")
    if gram:
        ozet_parts.append(f"gram altın {gram['value']:.0f}₺ ({_pct(gram.get('change'))})")
    ozet = ", ".join(ozet_parts) + ". "
    ozet += f"Küresel borsalarda {w_up} yükseliş / {w_down} düşüş ile hava {genel}. "
    if btc:
        ozet += f"Kripto tarafında Bitcoin {_pct(btc.get('change'))}. "
    ozet += "Gün geneli aşağıda bölüm bölüm değerlendirildi."

    kapanis = (
        f"Gün genelinde tablo {genel}. "
        + ("Risk iştahı görece canlı, seçici alımlar öne çıkıyor. " if genel == "pozitif"
           else "Temkinli ve savunmacı bir hava hâkim. " if genel == "negatif"
           else "Yönsüz, seçici ve dengeli bir seyir var. ")
        + "Bu değerlendirme veri temelli bir sentezdir, bireysel yatırım tavsiyesi değildir."
    )

    return {
        "ozet": ozet, "genel_hava": genel, "gunun_rakamlari": rakamlar,
        "bolumler": bolumler, "temalar": temalar, "one_cikan_haberler": haberler,
        "riskler": riskler, "firsatlar": firsatlar, "beklenti": beklenti,
        "kapanis": kapanis, "mode": "kural", "model": None,
    }


# ---------- cache + genel API ----------
def _load_cache() -> dict | None:
    global _mem_cache
    if _mem_cache is not None:
        return _mem_cache
    try:
        _mem_cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        _mem_cache = None
    return _mem_cache


def _save_cache(payload: dict) -> None:
    global _mem_cache
    _mem_cache = payload
    try:
        _CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def generate(db: Session) -> dict:
    """Raporu üretir (anahtar varsa AI, yoksa kural bazlı) ve cache'ler."""
    data = _collect(db)
    note = None
    report: dict
    if settings.anthropic_api_key:
        try:
            report = _llm_report(_brief_text(data))
        except Exception as e:  # noqa: BLE001
            report = _rule_report(data)
            note = f"AI üretimi başarısız ({type(e).__name__}); kural bazlı rapora düşüldü."
    else:
        report = _rule_report(data)

    payload = {
        "date": _today(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report": report,
        "note": note,
    }
    _save_cache(payload)
    return payload


def get_report(db: Session, force: bool = False) -> dict:
    """Bugünün raporu cache'te varsa onu, yoksa yeni üretir. force=True yeniden üretir."""
    cache = _load_cache()
    if not force and cache and cache.get("date") == _today():
        return cache
    return generate(db)
