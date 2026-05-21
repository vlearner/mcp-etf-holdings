# Top ~100 US ETFs by AUM used for reverse-lookup scans.
# Source: industry rankings as of early 2025.
TOP_ETFS: list[str] = [
    # Broad US equity
    "SPY", "IVV", "VOO", "VTI", "ITOT", "SCHB", "VV",
    # US large-cap growth / value
    "QQQ", "QQQM", "IWF", "VUG", "IVW", "SCHG",
    "IWD", "VTV", "IVE", "SCHV",
    # US mid-cap
    "IJH", "IWR", "VO", "MDY", "SCHM",
    # US small-cap
    "IWM", "IJR", "VB", "SCHA",
    # Dividend / income
    "VYM", "DVY", "SDY", "SCHD", "HDV", "VIG",
    # Sector – Technology
    "XLK", "VGT", "FTEC",
    # Sector – Health Care
    "XLV", "VHT",
    # Sector – Financials
    "XLF", "VFH",
    # Sector – Energy
    "XLE", "VDE",
    # Sector – Consumer Discretionary
    "XLY", "VCR",
    # Sector – Consumer Staples
    "XLP", "VDC",
    # Sector – Industrials
    "XLI", "VIS",
    # Sector – Materials
    "XLB", "VAW",
    # Sector – Utilities
    "XLU", "VPU",
    # Sector – Real Estate
    "XLRE", "VNQ",
    # Sector – Communication Services
    "XLC",
    # Thematic / factor
    "ARKK", "ARKW", "ARKG", "ARKF", "ARKQ",
    "ICLN", "JETS", "SOXX", "SMH", "HACK",
    "ROBO", "BOTZ", "AIQ",
    # International developed
    "EFA", "VEA", "IEFA", "SCHF", "VGK", "EWJ",
    # International emerging
    "EEM", "VWO", "IEMG", "SCHE",
    # Fixed income – broad
    "BND", "AGG", "SCHZ",
    # Fixed income – Treasury
    "TLT", "IEF", "SHY", "GOVT", "VGIT",
    # Fixed income – corporate
    "LQD", "HYG", "JNK", "VCIT",
    # Fixed income – TIPS
    "TIP", "VTIP",
    # Commodities
    "GLD", "IAU", "SLV", "USO", "DBC", "PDBC",
    # Multi-asset / balanced
    "AOR", "AOM", "AOA",
    # Leveraged / inverse (popular, included for coverage)
    "TQQQ", "SQQQ", "UPRO", "SPXU",
    # Cash / ultra-short
    "BIL", "SHV", "SGOV",
]
