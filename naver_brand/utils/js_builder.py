"""
JS 코드 동적 생성 유틸리티

settings.py 의 매핑 사전을 읽어, Playwright page.evaluate() 에 전달할
JS 코드 문자열을 생성한다. 크롤러 코드에 JS 속성 키가 직접 노출되지 않는다.

주의: Playwright evaluate 컨텍스트 호환을 위해
      ?. (optional chaining) 과 ?? (nullish coalescing) 를 사용하지 않는다.
      대신 && 체이닝과 || 폴백을 사용한다.
"""
import json
import config.settings as settings


def _dot_path_js(obj_var: str, dot_path: str) -> str:
    """
    'a.b.c' → && 체이닝으로 안전 접근하는 JS 코드를 반환한다.
    예: _dot_path_js('ch', 'businessAddressInfo.fullAddressInfo')
        → '(ch && ch.businessAddressInfo && ch.businessAddressInfo.fullAddressInfo)'
    """
    parts = dot_path.split(".")
    exprs = []
    current = obj_var
    for part in parts:
        exprs.append(current)
        current = f"{current}.{part}"
    exprs.append(current)
    return "(" + " && ".join(exprs) + ")"


def _resolve_js(obj_var: str, field_spec) -> str:
    """
    field_spec 이 문자열이면 단일 경로,
    리스트이면 폴백 체인(|| 연결) JS 를 반환한다.
    """
    if isinstance(field_spec, list):
        exprs = [_dot_path_js(obj_var, p) for p in field_spec]
        return "(" + " || ".join(exprs) + ")"
    return _dot_path_js(obj_var, field_spec)


# ═══════════════════════════════════════════════════════════════════
# 매장 정보 추출 JS
# ═══════════════════════════════════════════════════════════════════

def build_store_extract_js() -> str:
    """매장 정보 추출용 JS 코드 문자열을 반환한다."""
    fm = settings.STORE_FIELD_MAP
    sv = settings.STATE_VAR
    root = fm["root_key"]

    lines = [
        f"var state = window.{sv};",
        f"if (!state || !state.{root}) return null;",
        f"var ch = state.{root};",
        "return {",
    ]

    fields = {k: v for k, v in fm.items() if k != "root_key"}
    for key, spec in fields.items():
        js_expr = _resolve_js("ch", spec)
        lines.append(f"    {key}: {js_expr} || null,")

    lines.append("};")
    return "() => {\n" + "\n".join(f"    {l}" for l in lines) + "\n}"


# ═══════════════════════════════════════════════════════════════════
# 카테고리 목록 추출 JS
# ═══════════════════════════════════════════════════════════════════

def build_category_extract_js() -> str:
    """카테고리 목록 추출용 JS 코드 문자열을 반환한다."""
    fm = settings.PRODUCT_FIELD_MAP
    sv = settings.STATE_VAR
    cat_root = fm["category_root"]
    cat_list = fm["category_list"]

    id_expr = _resolve_js("c", fm["category_id"])
    name_expr = _resolve_js("c", fm["category_name"])

    return f"""() => {{
    var state = window.{sv};
    if (!state || !state.{cat_root}) return [];
    var menu = state.{cat_root};
    var items = menu.{cat_list} || [];
    return items.map(function(c) {{
        return {{
            id: {id_expr} || '',
            name: {name_expr} || 'N/A',
        }};
    }});
}}"""


# ═══════════════════════════════════════════════════════════════════
# 상품 목록 추출 JS
# ═══════════════════════════════════════════════════════════════════

def build_products_extract_js() -> str:
    """상품 목록 추출용 JS 코드 문자열을 반환한다."""
    fm = settings.PRODUCT_FIELD_MAP
    sv = settings.STATE_VAR
    pr = fm["products_root"]
    pl = fm["products_list"]
    tc = fm["total_count"]

    id_expr = _resolve_js("p", fm["product_id"])
    name_expr = _resolve_js("p", fm["product_name"])
    sale_expr = _resolve_js("p", fm["sale_price"])
    disc_price_expr = _resolve_js("p", fm["discounted_price"])
    disc_rate_expr = _resolve_js("p", fm["discount_rate"])
    img_expr = _resolve_js("p", fm["image_url"])
    rev_expr = _resolve_js("p", fm["review_count"])
    score_expr = _resolve_js("p", fm["average_score"])
    brand_expr = _resolve_js("p", fm["brand_name"])
    detail_expr = _resolve_js("p", fm["detail_text"])

    return f"""() => {{
    var state = window.{sv};
    if (!state || !state.{pr}) return null;
    var container = state.{pr};
    return {{
        totalCount: container.{tc} || 0,
        products: (container.{pl} || []).map(function(p) {{
            return {{
                id: {id_expr} || null,
                productNo: {id_expr} || null,
                name: {name_expr} || 'N/A',
                salePrice: {sale_expr} || 0,
                discountedPrice: {disc_price_expr} || {sale_expr} || 0,
                discountRate: {disc_rate_expr} || 0,
                imageUrl: {img_expr} || 'N/A',
                reviewCount: {rev_expr} || 0,
                averageScore: {score_expr} || 0,
                brandName: {brand_expr} || 'N/A',
                categoryName: (p && p.category && p.category.categoryName) || 'N/A',
                detailText: {detail_expr} || '',
            }};
        }}),
    }};
}}"""


# ═══════════════════════════════════════════════════════════════════
# 상품 상세 추출 JS
# ═══════════════════════════════════════════════════════════════════

def build_detail_extract_js() -> str:
    """상품 상세 추출용 JS 코드 문자열을 반환한다."""
    fm = settings.DETAIL_FIELD_MAP
    sv = settings.STATE_VAR
    roots = fm["detail_roots"]
    desc_path = fm["description"]
    imgs_path = fm["detail_images"]
    dom_sels = json.dumps(settings.DETAIL_DOM_SELECTORS)

    root_blocks = []
    for root_key in roots:
        desc_expr = _dot_path_js("obj", desc_path)
        imgs_expr = _dot_path_js("obj", imgs_path)
        # 변수명 충돌 방지: root_key 에서 하이픈 등 제거
        var_name = root_key.replace("-", "_")
        root_blocks.append(f"""
        var {var_name}_data = state.{root_key};
        if ({var_name}_data && typeof {var_name}_data === 'object') {{
            if (!({var_name}_data.A !== undefined && Object.keys({var_name}_data).length === 1)) {{
                var obj = {var_name}_data;
                return {{
                    description: {desc_expr} || '',
                    images: {imgs_expr} || [],
                }};
            }}
        }}""")

    root_js = "\n".join(root_blocks)

    return f"""() => {{
    var state = window.{sv};
    if (!state) return null;
    {root_js}

    var selectors = {dom_sels};
    for (var i = 0; i < selectors.length; i++) {{
        var viewer = document.querySelector(selectors[i]);
        if (viewer) {{
            var imgs = viewer.querySelectorAll('img');
            var imgList = [];
            for (var j = 0; j < imgs.length; j++) {{
                var src = imgs[j].src;
                if (src && src.indexOf('icon') === -1) imgList.push(src);
            }}
            return {{
                description: viewer.innerText.substring(0, 2000),
                images: imgList,
            }};
        }}
    }}
    return null;
}}"""


# ═══════════════════════════════════════════════════════════════════
# URL 패턴 빌더
# ═══════════════════════════════════════════════════════════════════

def build_category_url(cat_id: str, page: int) -> str:
    """카테고리 페이지 URL 을 반환한다."""
    pattern = settings.URL_PATTERNS["category_page"]
    return settings.BASE_URL + pattern.format(
        slug=settings.STORE_SLUG, cat_id=cat_id, page=page,
    )


def build_product_url(product_id: str) -> str:
    """상품 상세 페이지 URL 을 반환한다."""
    pattern = settings.URL_PATTERNS["product_page"]
    return settings.BASE_URL + pattern.format(
        slug=settings.STORE_SLUG, product_id=product_id,
    )
