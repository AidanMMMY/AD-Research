"""CSRC (Tushare) → GICS Industry Classification Mapping.

Maps Tushare stock_basic ``industry`` values (CSRC 2012 classification for
China A-share stocks) to GICS sector and industry names used by the
``etf_info.sector`` and ``etf_info.industry`` columns.

Coverage
--------
Covers all ~90 CSRC industries returned by Tushare for the ~5000 listed
A-share stocks. Unknown industries are mapped to (None, None).

Sources
-------
- Tushare stock_basic API (industry field)
- GICS 2023 structure (S&P Global / MSCI)
"""

# ---------------------------------------------------------------------------
# CSRC Industry Name → (GICS Sector, GICS Industry)
# ---------------------------------------------------------------------------

CSRC_TO_GICS: dict[str, tuple[str, str]] = {
    # =====================================================================
    # Financials (GICS 40)
    # =====================================================================
    "银行": ("Financials", "Banks"),
    "保险": ("Financials", "Insurance"),
    "证券": ("Financials", "Capital Markets"),
    "多元金融": ("Financials", "Diversified Financial Services"),
    "其他金融": ("Financials", "Diversified Financial Services"),
    "信托": ("Financials", "Capital Markets"),
    "金融控股": ("Financials", "Diversified Financial Services"),

    # =====================================================================
    # Information Technology (GICS 45)
    # =====================================================================
    "半导体": ("Information Technology", "Semiconductors"),
    "软件服务": ("Information Technology", "Software"),
    "元器件": ("Information Technology", "Electronic Components"),
    "通信设备": ("Information Technology", "Communications Equipment"),
    "IT设备": ("Information Technology", "Technology Hardware & Equipment"),
    "电脑设备": ("Information Technology", "Technology Hardware & Equipment"),
    "电子制造": ("Information Technology", "Electronic Manufacturing Services"),
    "光电": ("Information Technology", "Electronic Components"),
    "电器仪表": ("Information Technology", "Electronic Equipment & Instruments"),
    "电信设备": ("Information Technology", "Communications Equipment"),
    "电子器件": ("Information Technology", "Electronic Components"),
    "软件": ("Information Technology", "Software"),

    # =====================================================================
    # Communication Services (GICS 50)
    # =====================================================================
    "互联网": ("Communication Services", "Interactive Media & Services"),
    "传媒娱乐": ("Communication Services", "Media & Entertainment"),
    "电信运营": ("Communication Services", "Diversified Telecommunication"),
    "广告包装": ("Communication Services", "Media"),
    "出版业": ("Communication Services", "Publishing"),
    "影视音像": ("Communication Services", "Entertainment"),
    "网络游戏": ("Communication Services", "Interactive Home Entertainment"),
    "文化传媒": ("Communication Services", "Media & Entertainment"),
    "营销传播": ("Communication Services", "Advertising"),

    # =====================================================================
    # Consumer Discretionary (GICS 25)
    # =====================================================================
    "家用电器": ("Consumer Discretionary", "Household Appliances"),
    "汽车类": ("Consumer Discretionary", "Automobile Manufacturers"),
    "汽车整车": ("Consumer Discretionary", "Automobile Manufacturers"),
    "汽车配件": ("Consumer Discretionary", "Auto Parts & Equipment"),
    "汽车服务": ("Consumer Discretionary", "Automotive Retail"),
    "摩托车": ("Consumer Discretionary", "Motorcycle Manufacturers"),
    "纺织服饰": ("Consumer Discretionary", "Textiles & Apparel"),
    "服饰": ("Consumer Discretionary", "Apparel & Accessories"),
    "纺织": ("Consumer Discretionary", "Textiles"),
    "商业连锁": ("Consumer Discretionary", "Specialty Retail"),
    "商贸代理": ("Consumer Discretionary", "Distributors"),
    "旅游": ("Consumer Discretionary", "Hotels, Resorts & Cruise Lines"),
    "酒店餐饮": ("Consumer Discretionary", "Restaurants"),
    "旅游服务": ("Consumer Discretionary", "Leisure Facilities"),
    "文教休闲": ("Consumer Discretionary", "Leisure Products"),
    "家居用品": ("Consumer Discretionary", "Home Furnishings"),
    "装修装饰": ("Consumer Discretionary", "Home Improvement Retail"),
    "家用轻工": ("Consumer Discretionary", "Housewares & Specialties"),
    "日用百货": ("Consumer Discretionary", "Department Stores"),
    "教育培训": ("Consumer Discretionary", "Education Services"),
    "体育": ("Consumer Discretionary", "Leisure Products"),
    "玩具": ("Consumer Discretionary", "Leisure Products"),
    "其他商业": ("Consumer Discretionary", "Specialty Retail"),
    "商品城": ("Consumer Discretionary", "Specialty Retail"),
    "电器连锁": ("Consumer Discretionary", "Specialty Retail"),
    "百货": ("Consumer Discretionary", "Department Stores"),
    "批发业": ("Consumer Discretionary", "Distributors"),
    "旅游景点": ("Consumer Discretionary", "Leisure Facilities"),

    # =====================================================================
    # Consumer Staples (GICS 30)
    # =====================================================================
    "白酒": ("Consumer Staples", "Distillers & Vintners"),
    "啤酒": ("Consumer Staples", "Brewers"),
    "红黄酒": ("Consumer Staples", "Distillers & Vintners"),
    "食品": ("Consumer Staples", "Packaged Foods & Meats"),
    "食品饮料": ("Consumer Staples", "Soft Drinks & Non-alcoholic Beverages"),
    "酿酒": ("Consumer Staples", "Distillers & Vintners"),
    "软饮料": ("Consumer Staples", "Soft Drinks & Non-alcoholic Beverages"),
    "乳制品": ("Consumer Staples", "Packaged Foods & Meats"),
    "调味品": ("Consumer Staples", "Packaged Foods & Meats"),
    "农林牧渔": ("Consumer Staples", "Agricultural Products"),
    "农业综合": ("Consumer Staples", "Agricultural Products"),
    "种植业": ("Consumer Staples", "Agricultural Products"),
    "渔业": ("Consumer Staples", "Agricultural Products"),
    "畜牧": ("Consumer Staples", "Agricultural Products"),
    "饲料": ("Consumer Staples", "Agricultural Products"),
    "日用化工": ("Consumer Staples", "Household Products"),
    "个人用品": ("Consumer Staples", "Personal Products"),
    "烟草": ("Consumer Staples", "Tobacco"),
    "超市连锁": ("Consumer Staples", "Food Retail"),

    # =====================================================================
    # Health Care (GICS 35)
    # =====================================================================
    "医药": ("Health Care", "Pharmaceuticals"),
    "化学制药": ("Health Care", "Pharmaceuticals"),
    "中药": ("Health Care", "Pharmaceuticals"),
    "中成药": ("Health Care", "Pharmaceuticals"),
    "生物制药": ("Health Care", "Biotechnology"),
    "医疗保健": ("Health Care", "Health Care Equipment"),
    "医疗器械": ("Health Care", "Health Care Equipment"),
    "医药商业": ("Health Care", "Health Care Distributors"),
    "医疗服务": ("Health Care", "Health Care Services"),
    "生物制品": ("Health Care", "Biotechnology"),
    "化学制剂": ("Health Care", "Pharmaceuticals"),
    "原料药": ("Health Care", "Pharmaceuticals"),

    # =====================================================================
    # Energy (GICS 10)
    # =====================================================================
    "煤炭": ("Energy", "Coal & Consumable Fuels"),
    "煤炭开采": ("Energy", "Coal & Consumable Fuels"),
    "石油": ("Energy", "Oil & Gas Exploration & Production"),
    "石油开采": ("Energy", "Oil & Gas Exploration & Production"),
    "石油加工": ("Energy", "Oil & Gas Refining & Marketing"),
    "石油贸易": ("Energy", "Oil & Gas Storage & Transportation"),
    "油服": ("Energy", "Oil & Gas Equipment & Services"),
    "天然气": ("Energy", "Oil & Gas Storage & Transportation"),
    "供气供热": ("Energy", "Gas Utilities"),
    "焦炭加工": ("Energy", "Coal & Consumable Fuels"),

    # =====================================================================
    # Utilities (GICS 55)
    # =====================================================================
    "电力": ("Utilities", "Electric Utilities"),
    "水力发电": ("Utilities", "Renewable Electricity"),
    "火力发电": ("Utilities", "Electric Utilities"),
    "新型电力": ("Utilities", "Renewable Electricity"),
    "水务": ("Utilities", "Water Utilities"),
    "环保": ("Utilities", "Water & Waste Management"),
    "环境保护": ("Utilities", "Water & Waste Management"),

    # =====================================================================
    # Materials (GICS 15)
    # =====================================================================
    "钢铁": ("Materials", "Steel"),
    "特种钢": ("Materials", "Steel"),
    "普钢": ("Materials", "Steel"),
    "钢加工": ("Materials", "Steel"),
    "有色": ("Materials", "Diversified Metals & Mining"),
    "小金属": ("Materials", "Diversified Metals & Mining"),
    "黄金": ("Materials", "Precious Metals & Minerals"),
    "铜": ("Materials", "Copper"),
    "铝": ("Materials", "Aluminum"),
    "铅锌": ("Materials", "Diversified Metals & Mining"),
    "稀土": ("Materials", "Diversified Metals & Mining"),
    "化工": ("Materials", "Commodity Chemicals"),
    "化工原料": ("Materials", "Commodity Chemicals"),
    "化纤": ("Materials", "Specialty Chemicals"),
    "化学制品": ("Materials", "Specialty Chemicals"),
    "农药化肥": ("Materials", "Fertilizers & Agricultural Chemicals"),
    "日用化学": ("Materials", "Specialty Chemicals"),
    "建材": ("Materials", "Construction Materials"),
    "水泥": ("Materials", "Construction Materials"),
    "玻璃": ("Materials", "Construction Materials"),
    "其他建材": ("Materials", "Construction Materials"),
    "陶瓷": ("Materials", "Construction Materials"),
    "造纸": ("Materials", "Paper & Forest Products"),
    "林业": ("Materials", "Paper & Forest Products"),
    "矿物制品": ("Materials", "Construction Materials"),
    "塑料": ("Materials", "Specialty Chemicals"),
    "橡胶": ("Materials", "Specialty Chemicals"),
    "无机盐": ("Materials", "Commodity Chemicals"),
    "涂料": ("Materials", "Specialty Chemicals"),
    "染料": ("Materials", "Specialty Chemicals"),
    "染料涂料": ("Materials", "Specialty Chemicals"),
    "聚氨酯": ("Materials", "Specialty Chemicals"),
    "煤化工": ("Materials", "Commodity Chemicals"),
    "精细化工": ("Materials", "Specialty Chemicals"),
    "氟化工": ("Materials", "Specialty Chemicals"),

    # =====================================================================
    # Industrials (GICS 20)
    # =====================================================================
    "航空": ("Industrials", "Aerospace & Defense"),
    "船舶": ("Industrials", "Industrial Machinery"),
    "工程机械": ("Industrials", "Construction Machinery & Heavy Trucks"),
    "工业机械": ("Industrials", "Industrial Machinery"),
    "通用机械": ("Industrials", "Industrial Machinery"),
    "电气设备": ("Industrials", "Electrical Components & Equipment"),
    "运输设备": ("Industrials", "Industrial Machinery"),
    "专用机械": ("Industrials", "Industrial Machinery"),
    "机械基件": ("Industrials", "Industrial Machinery"),
    "纺织机械": ("Industrials", "Industrial Machinery"),
    "农用机械": ("Industrials", "Agricultural & Farm Machinery"),
    "轻工机械": ("Industrials", "Industrial Machinery"),
    "机床制造": ("Industrials", "Industrial Machinery"),
    "建筑施工": ("Industrials", "Construction & Engineering"),
    "建筑工程": ("Industrials", "Construction & Engineering"),
    "公路": ("Industrials", "Highways & Railtracks"),
    "路桥": ("Industrials", "Highways & Railtracks"),
    "机场": ("Industrials", "Airport Services"),
    "水运": ("Industrials", "Marine Ports & Services"),
    "化工机械": ("Industrials", "Industrial Machinery"),
    "港口": ("Industrials", "Marine Ports & Services"),
    "空运": ("Industrials", "Airlines"),
    "铁路": ("Industrials", "Railroads"),
    "公共交通": ("Industrials", "Trucking"),
    "交通设施": ("Industrials", "Airport Services"),
    "仓储物流": ("Industrials", "Air Freight & Logistics"),
    "运输服务": ("Industrials", "Trucking"),
    "交通运输": ("Industrials", "Transportation Infrastructure"),
    "物流": ("Industrials", "Air Freight & Logistics"),
    "综合类": ("Industrials", "Industrial Conglomerates"),

    # =====================================================================
    # Real Estate (GICS 60)
    # =====================================================================
    "房地产": ("Real Estate", "Real Estate Development"),
    "房产服务": ("Real Estate", "Real Estate Services"),
    "园区开发": ("Real Estate", "Real Estate Development"),
    "区域地产": ("Real Estate", "Real Estate Development"),
    "商业地产": ("Real Estate", "Real Estate Operating Companies"),
    "全国地产": ("Real Estate", "Real Estate Development"),
}


def map_industry(csrc_industry: str | None) -> tuple[str | None, str | None]:
    """Map a Tushare/CSRC industry name to (GICS sector, GICS industry).

    Returns (None, None) when the industry is unrecognised or None.
    """
    if not csrc_industry:
        return None, None

    result = CSRC_TO_GICS.get(csrc_industry)
    if result is None:
        # Normalise common variations (strip whitespace, try direct match)
        cleaned = csrc_industry.strip()
        result = CSRC_TO_GICS.get(cleaned)

    return result if result is not None else (None, None)
