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
