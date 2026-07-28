# ~365 major US-listed ETFs used for reverse-lookup scans.
# Curated by AUM and category coverage; source: industry rankings as of early 2025.
# Non-equity funds (bonds, commodities) return empty holdings and are cached
# as such, so they add negligible cost to repeat scans.
TOP_ETFS: list[str] = [
    # Broad US equity
    "SPY", "IVV", "VOO", "VTI", "ITOT", "SCHB", "SPLG", "VV", "RSP",
    "SCHX", "IWB", "OEF", "MGC", "VONE", "DSI", "ESGU",
    # US large-cap growth
    "QQQ", "QQQM", "IWF", "VUG", "IVW", "SCHG", "MGK", "SPYG", "VONG", "IWY",
    # US large-cap value
    "IWD", "VTV", "IVE", "SCHV", "MGV", "SPYV", "VONV",
    # US mid-cap
    "IJH", "IWR", "VO", "MDY", "SCHM", "IVOO", "VOT", "VOE", "IWP", "IWS",
    # US small-cap
    "IWM", "IJR", "VB", "SCHA", "VTWO", "VIOO", "VBR", "VBK",
    "IWN", "IWO", "SLYV", "SLYG",
    # Dividend / income
    "VYM", "DVY", "SDY", "SCHD", "HDV", "VIG", "NOBL", "DGRO", "DGRW",
    "RDVY", "SPHD", "SPYD", "FVD", "DLN", "DON",
    "JEPI", "JEPQ", "QYLD", "XYLD", "RYLD", "DIVO",
    # Factor / smart beta
    "MTUM", "QUAL", "VLUE", "USMV", "SPLV", "EFAV", "EEMV", "SPHQ",
    "COWZ", "CALF", "MOAT", "FNDX", "FNDA", "PRF",
    "AVUV", "AVDV", "AVEM", "DFAC", "DFAT", "DFUS",
    # Sector – Technology / semiconductors / software
    "XLK", "VGT", "FTEC", "IYW", "IGV", "SOXX", "SMH", "XSD", "PSI",
    # Sector – Health Care / biotech
    "XLV", "VHT", "IYH", "IBB", "XBI", "IHI", "XPH",
    # Sector – Financials / banks
    "XLF", "VFH", "IYF", "KRE", "KBE", "KBWB", "IAI",
    # Sector – Energy
    "XLE", "VDE", "IYE", "XOP", "OIH", "AMLP",
    # Sector – Consumer Discretionary / retail
    "XLY", "VCR", "IYC", "XRT", "FDIS",
    # Sector – Consumer Staples
    "XLP", "VDC", "IYK", "FSTA",
    # Sector – Industrials / defense / transport
    "XLI", "VIS", "IYJ", "ITA", "PPA", "XAR", "IYT", "XTN",
    # Sector – Materials / metals & mining
    "XLB", "VAW", "IYM", "XME", "GDX", "GDXJ", "SIL", "COPX", "LIT", "URA",
    # Sector – Utilities
    "XLU", "VPU", "IDU",
    # Sector – Real Estate
    "XLRE", "VNQ", "IYR", "SCHH", "RWR", "REZ", "VNQI",
    # Sector – Communication Services
    "XLC", "VOX", "FCOM",
    # Thematic / innovation
    "ARKK", "ARKW", "ARKG", "ARKF", "ARKQ", "ARKX",
    "ICLN", "TAN", "FAN", "PBW", "QCLN",
    "JETS", "HACK", "CIBR", "BUG",
    "ROBO", "BOTZ", "AIQ", "IRBO",
    "SKYY", "WCLD", "CLOU", "FINX", "IPAY", "ESPO",
    "BLOK", "MSOS", "DRIV", "IDRV", "KARS",
    "MOO", "PHO", "PAVE", "IFRA", "GRID",
    # International – global / total world
    "VT", "ACWI", "ACWX", "VXUS", "IXUS", "IOO", "IXN",
    # International – developed
    "EFA", "VEA", "IEFA", "SCHF", "SPDW", "IDEV", "VGK", "EZU",
    "EWJ", "EWU", "EWG", "EWQ", "EWC", "EWA", "EWY", "EWT", "EWH", "EWS",
    "DXJ", "HEFA", "HEDJ",
    # International – emerging
    "EEM", "VWO", "IEMG", "SCHE", "SPEM", "EMXC", "FNDE", "DGS",
    "EWZ", "EWW", "INDA", "FXI", "MCHI", "KWEB",
    # Fixed income – broad
    "BND", "AGG", "SCHZ", "BNDX", "BNDW", "FBND", "IUSB",
    # Fixed income – Treasury
    "TLT", "IEF", "SHY", "GOVT", "VGIT", "VGSH", "VGLT", "EDV", "TLH",
    "SPTL", "SPTS", "SPTI", "BIL", "SHV", "SGOV", "USFR", "TFLO",
    # Fixed income – corporate / high yield
    "LQD", "VCIT", "VCSH", "VCLT", "IGIB", "IGSB",
    "HYG", "JNK", "USHY", "SHYG", "HYLB", "SJNK", "BKLN", "SRLN", "ANGL", "FALN",
    # Fixed income – municipal
    "MUB", "VTEB", "TFI", "HYD", "SHM", "SUB",
    # Fixed income – TIPS
    "TIP", "VTIP", "SCHP", "STIP",
    # Fixed income – mortgage-backed
    "MBB", "VMBS", "SPMB",
    # Fixed income – emerging market debt
    "EMB", "PCY", "EBND", "VWOB",
    # Cash / ultra-short
    "FLOT", "MINT", "JPST", "GSY", "ICSH", "NEAR",
    # Commodities
    "GLD", "IAU", "GLDM", "SGOL", "SLV", "SIVR", "PPLT", "PALL",
    "USO", "BNO", "UNG", "DBC", "PDBC", "GSG", "DBA",
    "CORN", "WEAT", "CPER", "DBB",
    # Crypto-linked
    "IBIT", "FBTC", "ARKB", "BITB", "GBTC", "BITO", "ETHA", "ETHE",
    # Multi-asset / balanced
    "AOR", "AOM", "AOA", "AOK",
    # Leveraged / inverse (popular, included for coverage)
    "TQQQ", "SQQQ", "UPRO", "SPXU", "SSO", "SDS", "QLD", "QID", "PSQ", "SH",
    "TNA", "TZA", "SPXL", "SPXS", "SOXL", "SOXS", "TECL", "FAS", "FAZ",
    "LABU", "TMF", "TMV", "NUGT", "UVXY", "VIXY", "SVXY", "UDOW", "SDOW",
]

# Curated keyword index over the funds above, used to top up Yahoo's ETF search.
#
# Yahoo's search API answers "S&P 500" with indices and futures that the ETF
# filter drops, and "bitcoin" with GBTC alone while IBIT and FBTC — both listed
# above — never appear. Each entry maps the words people actually search for to
# funds already in TOP_ETFS.
#
# The names here are static labels for search output only; every tool that
# reports data (etf_info, compare_etfs, …) reads it live from Yahoo, so a fund
# renamed by its issuer misprints a search row and nothing else.
ETF_THEMES: dict[str, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = {
    "S&P 500": (
        ("s&p 500", "s&p500", "sp 500", "sp500", "spx", "500 index"),
        (
            ("SPY", "SPDR S&P 500 ETF Trust"),
            ("IVV", "iShares Core S&P 500 ETF"),
            ("VOO", "Vanguard S&P 500 ETF"),
            ("SPLG", "SPDR Portfolio S&P 500 ETF"),
            ("RSP", "Invesco S&P 500 Equal Weight ETF"),
        ),
    ),
    "Total market": (
        ("total market", "total stock market", "whole market", "entire market"),
        (
            ("VTI", "Vanguard Total Stock Market ETF"),
            ("ITOT", "iShares Core S&P Total U.S. Stock Market ETF"),
            ("SCHB", "Schwab U.S. Broad Market ETF"),
            ("VT", "Vanguard Total World Stock ETF"),
        ),
    ),
    "Nasdaq 100": (
        ("nasdaq", "nasdaq 100", "nasdaq100"),
        (
            ("QQQ", "Invesco QQQ Trust"),
            ("QQQM", "Invesco NASDAQ 100 ETF"),
        ),
    ),
    "Bitcoin": (
        ("bitcoin", "btc", "crypto", "cryptocurrency"),
        (
            ("IBIT", "iShares Bitcoin Trust ETF"),
            ("FBTC", "Fidelity Wise Origin Bitcoin Fund"),
            ("ARKB", "ARK 21Shares Bitcoin ETF"),
            ("BITB", "Bitwise Bitcoin ETF"),
            ("GBTC", "Grayscale Bitcoin Trust ETF"),
            ("BITO", "ProShares Bitcoin Strategy ETF"),
        ),
    ),
    "Ethereum": (
        ("ethereum", "ether", "eth", "crypto", "cryptocurrency"),
        (
            ("ETHA", "iShares Ethereum Trust ETF"),
            ("ETHE", "Grayscale Ethereum Trust ETF"),
        ),
    ),
    "Precious metals": (
        ("gold", "silver", "precious metals", "bullion"),
        (
            ("GLD", "SPDR Gold Shares"),
            ("IAU", "iShares Gold Trust"),
            ("GLDM", "SPDR Gold MiniShares Trust"),
            ("SLV", "iShares Silver Trust"),
        ),
    ),
    "Semiconductors": (
        ("semiconductor", "semiconductors", "semis", "chips", "chipmakers"),
        (
            ("SOXX", "iShares Semiconductor ETF"),
            ("SMH", "VanEck Semiconductor ETF"),
            ("XSD", "SPDR S&P Semiconductor ETF"),
            ("PSI", "Invesco Semiconductors ETF"),
        ),
    ),
    "Technology": (
        ("technology", "tech sector", "information technology"),
        (
            ("XLK", "Technology Select Sector SPDR Fund"),
            ("VGT", "Vanguard Information Technology ETF"),
            ("IGV", "iShares Expanded Tech-Software Sector ETF"),
        ),
    ),
    "Artificial intelligence": (
        ("artificial intelligence", "robotics", "automation"),
        (
            ("AIQ", "Global X Artificial Intelligence & Technology ETF"),
            ("BOTZ", "Global X Robotics & Artificial Intelligence ETF"),
            ("ROBO", "ROBO Global Robotics and Automation Index ETF"),
        ),
    ),
    "Cybersecurity": (
        ("cybersecurity", "cyber security", "security software"),
        (
            ("CIBR", "First Trust NASDAQ Cybersecurity ETF"),
            ("HACK", "Amplify Cybersecurity ETF"),
            ("BUG", "Global X Cybersecurity ETF"),
        ),
    ),
    "Clean energy": (
        ("clean energy", "renewable energy", "solar"),
        (
            ("ICLN", "iShares Global Clean Energy ETF"),
            ("TAN", "Invesco Solar ETF"),
            ("QCLN", "First Trust NASDAQ Clean Edge Green Energy Index Fund"),
        ),
    ),
    "Dividend": (
        ("dividend", "dividends", "income", "high yield equity"),
        (
            ("SCHD", "Schwab U.S. Dividend Equity ETF"),
            ("VYM", "Vanguard High Dividend Yield ETF"),
            ("VIG", "Vanguard Dividend Appreciation ETF"),
            ("DGRO", "iShares Core Dividend Growth ETF"),
            ("NOBL", "ProShares S&P 500 Dividend Aristocrats ETF"),
        ),
    ),
    "Real estate": (
        ("real estate", "reit", "reits"),
        (
            ("VNQ", "Vanguard Real Estate ETF"),
            ("XLRE", "Real Estate Select Sector SPDR Fund"),
            ("SCHH", "Schwab U.S. REIT ETF"),
        ),
    ),
    "Emerging markets": (
        ("emerging markets", "emerging market"),
        (
            ("VWO", "Vanguard FTSE Emerging Markets ETF"),
            ("IEMG", "iShares Core MSCI Emerging Markets ETF"),
            ("EEM", "iShares MSCI Emerging Markets ETF"),
        ),
    ),
    "International developed": (
        ("international", "developed markets", "ex us", "ex-us", "eafe"),
        (
            ("VXUS", "Vanguard Total International Stock ETF"),
            ("VEA", "Vanguard FTSE Developed Markets ETF"),
            ("IEFA", "iShares Core MSCI EAFE ETF"),
            ("EFA", "iShares MSCI EAFE ETF"),
        ),
    ),
    "Bonds": (
        ("bond", "bonds", "fixed income", "treasury", "treasuries"),
        (
            ("BND", "Vanguard Total Bond Market ETF"),
            ("AGG", "iShares Core U.S. Aggregate Bond ETF"),
            ("TLT", "iShares 20+ Year Treasury Bond ETF"),
            ("SGOV", "iShares 0-3 Month Treasury Bond ETF"),
        ),
    ),
}


def local_etf_matches(query: str) -> list[tuple[str, str]]:
    """Return curated (ticker, name) pairs whose theme keywords appear in `query`.

    Matching is on whole words, so "eth" matches "ethereum etf" but not
    "something else", and punctuation is folded to spaces so "semiconductor?"
    still matches. `&` survives folding because "S&P 500" needs it.
    """
    if not isinstance(query, str):
        return []

    folded = "".join(c if (c.isalnum() or c == "&") else " " for c in query.lower())
    text = f" {' '.join(folded.split())} "
    if not text.strip():
        return []

    matches: list[tuple[str, str]] = []
    seen: set[str] = set()
    for keywords, funds in ETF_THEMES.values():
        if not any(f" {keyword} " in text for keyword in keywords):
            continue
        for ticker, name in funds:
            if ticker not in seen:
                seen.add(ticker)
                matches.append((ticker, name))
    return matches
