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

_SCHEMA = {
    "type": "object",
    "properties": {
        "ozet": {"type": "string"},
        "genel_hava": {"type": "string", "enum": _SENTIMENTS},
        "bolumler": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string"},
                    "yorum": {"type": "string"},
                    "hava": {"type": "string", "enum": _SENTIMENTS},
                },
                "required": ["baslik", "yorum", "hava"],
                "additionalProperties": False,
            },
        },
        "one_cikan_haberler": {"type": "array", "items": {"type": "string"}},
        "riskler": {"type": "array", "items": {"type": "string"}},
        "kapanis": {"type": "string"},
    },
    "required": ["ozet", "genel_hava", "bolumler", "one_cikan_haberler", "riskler", "kapanis"],
    "additionalProperties": False,
}

_SYSTEM = (
    "Sen deneyimli, tarafsız bir Türk piyasa analistisin. Sana günün BİST, emtia, "
    "döviz, küresel borsa, kripto ve TEFAS fon verileriyle öne çıkan haber başlıkları "
    "verilecek. Bunları sentezleyip Türkçe, kısa ve net bir GÜNLÜK DEĞERLENDİRME raporu "
    "üret. Piyasa yorumcularının bakış açısını, verileri ve kendi dengeli yorumunu "
    "harmanla. Kurallar: yalnızca verilen verilere ve genel piyasa bağlamına dayan, "
    "uydurma rakam/isim ekleme; bireysel yatırım tavsiyesi verme (al/sat deme); "
    "abartıdan kaçın, gözlem ve olasılık dilini kullan. Sayıları verideki gibi aktar."
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
        "\nGörev: Yukarıdaki günün verileriyle şemaya uygun bir günlük değerlendirme "
        "raporu üret. Bölümler en az BİST, Emtia, Döviz & Küresel, Kripto ve Fonlar "
        "başlıklarını içersin. one_cikan_haberler'e en önemli 3-5 başlığı sadeleştirerek koy."
    )
    return "\n".join(lines)


# ---------- LLM raporu ----------
def _llm_report(brief: str) -> dict:
    import anthropic  # yalnızca anahtar varken gerekli

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.ai_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _SCHEMA}},
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
    dolar = _find(snap, "Dolar")
    euro = _find(snap, "Euro")
    gram = _find(snap, "Gram Altın")

    world_items = [i for i in d["world"].get("items", []) if i.get("change") is not None]
    w_up = sum(1 for i in world_items if i["change"] > 0)
    w_down = sum(1 for i in world_items if i["change"] < 0)

    def top(m, key, rev):
        arr = m.get(key, [])
        return arr[0] if arr else None

    bg = top(d["bist"], "gainers", True)
    bl = top(d["bist"], "losers", False)
    cg = top(d["crypto"], "gainers", True)
    cl = top(d["crypto"], "losers", False)
    fg = d["fon_gainers"][0] if d["fon_gainers"] else None
    fl = d["fon_losers"][0] if d["fon_losers"] else None

    metals = {m["key"]: m for m in d["metals"].get("metals", [])}
    brent = metals.get("brent")

    ozet_parts = []
    if bist100:
        ozet_parts.append(f"BİST 100 {bist100['value']:.0f} ({_pct(bist100.get('change'))})")
    if dolar:
        ozet_parts.append(f"Dolar/TL {dolar['value']:.2f}")
    if gram:
        ozet_parts.append(f"gram altın {gram['value']:.0f}₺ ({_pct(gram.get('change'))})")
    ozet = ", ".join(ozet_parts) + "."
    if world_items:
        ozet += f" Küresel borsalarda {w_up} yükseliş / {w_down} düşüş."

    bolumler = []

    b_txt = ""
    if bist100:
        b_txt += f"BİST 100 günü {_pct(bist100.get('change'))} değişimle geçiriyor. "
    if bg:
        b_txt += f"En çok yükselen {bg['code']} ({_pct(bg.get('change'))}). "
    if bl:
        b_txt += f"En çok düşen {bl['code']} ({_pct(bl.get('change'))})."
    bolumler.append({"baslik": "BİST", "yorum": b_txt.strip() or "Veri sınırlı.",
                     "hava": _sign(bist100.get("change") if bist100 else None)})

    e_txt = ""
    if gram:
        e_txt += f"Gram altın {gram['value']:.0f}₺ ({_pct(gram.get('change'))}). "
    if brent:
        e_txt += f"Brent petrol {brent['usd_price']:.1f}$ ({_pct(brent.get('usd_change'))})."
    bolumler.append({"baslik": "Emtia", "yorum": e_txt.strip() or "Veri sınırlı.",
                     "hava": _sign(gram.get("change") if gram else None)})

    d_txt = ""
    if dolar:
        d_txt += f"Dolar/TL {dolar['value']:.2f} ({_pct(dolar.get('change'))}). "
    if euro:
        d_txt += f"Euro/TL {euro['value']:.2f} ({_pct(euro.get('change'))}). "
    d_txt += f"Küresel tarafta {w_up} endeks/emtia yükseldi, {w_down} geriledi."
    bolumler.append({"baslik": "Döviz & Küresel", "yorum": d_txt.strip(),
                     "hava": "pozitif" if w_up > w_down else "negatif" if w_down > w_up else "karışık"})

    btc = _find(d["crypto_board"].get("items", []), "Bitcoin")
    c_txt = ""
    if btc:
        c_txt += f"Bitcoin {btc['value']:,.0f}$ ({_pct(btc.get('change'))}). "
    if cg:
        c_txt += f"Günün yükseleni {cg['code']} ({_pct(cg.get('change'))}), "
    if cl:
        c_txt += f"düşeni {cl['code']} ({_pct(cl.get('change'))})."
    bolumler.append({"baslik": "Kripto", "yorum": c_txt.strip() or "Veri sınırlı.",
                     "hava": _sign(btc.get("change") if btc else None)})

    f_txt = ""
    if fg:
        f_txt += f"En çok kazandıran fon {fg['code']} ({_pct(fg.get('change'))}). "
    if fl:
        f_txt += f"En çok kaybettiren {fl['code']} ({_pct(fl.get('change'))})."
    bolumler.append({"baslik": "Fonlar", "yorum": f_txt.strip() or "Veri sınırlı.",
                     "hava": _sign(fg.get("change") if fg else None)})

    haberler = []
    seen = set()
    for topic in ("bist", "general", "metals", "crypto", "world"):
        for n in d["news"].get(topic, [])[:2]:
            t = (n.get("title") or "").strip()
            if t and t not in seen:
                seen.add(t)
                haberler.append(t)
        if len(haberler) >= 5:
            break

    riskler = []
    for m in d["metals"].get("metals", []):
        if (m.get("usd_change") or 0) <= -0.02:
            riskler.append(f"{m['name']} sert geriledi ({_pct(m['usd_change'])}).")
    if bl and (bl.get("change") or 0) <= -0.03:
        riskler.append(f"{bl['code']} BİST'te belirgin düşüş ({_pct(bl['change'])}).")
    vix = _find(d["world"].get("items", []), "VIX (Korku Endeksi)")
    if vix and vix.get("value", 0) and vix["value"] >= 20:
        riskler.append(f"VIX korku endeksi yüksek ({vix['value']:.1f}).")
    if not riskler:
        riskler.append("Belirgin bir uç risk sinyali öne çıkmıyor; volatilite normal aralıkta.")

    signs = [b["hava"] for b in bolumler]
    pos, neg = signs.count("pozitif"), signs.count("negatif")
    genel = "pozitif" if pos > neg else "negatif" if neg > pos else "karışık"
    kapanis = (
        f"Gün genelinde tablo {genel}. "
        + ("Risk iştahı görece canlı. " if genel == "pozitif" else
           "Temkinli bir hava hâkim. " if genel == "negatif" else "Yönsüz, seçici bir seyir var. ")
        + "Bu değerlendirme veri temelli bir özettir, yatırım tavsiyesi değildir."
    )

    return {
        "ozet": ozet, "genel_hava": genel, "bolumler": bolumler,
        "one_cikan_haberler": haberler, "riskler": riskler, "kapanis": kapanis,
        "mode": "kural", "model": None,
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
