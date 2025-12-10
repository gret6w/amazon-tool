import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image
import json
import io
import zipfile
import base64

# ================= 1. 配置与美化 (复刻 React UI 风格) =================
st.set_page_config(page_title="Amazon Listing Architect", page_icon="🚀", layout="wide")

# 注入 CSS: 复刻 Tailwind CSS 的 Slate/Indigo 风格 + 亚马逊预览样式
st.markdown("""
<style>
    /* 全局字体与背景 */
    .stApp { background-color: #F8FAFC; font-family: 'Inter', sans-serif; }
    
    /* 卡片风格 */
    .css-card {
        background-color: white;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 24px;
    }
    
    /* 步骤条样式 */
    .step-active { color: #4F46E5; font-weight: bold; border-bottom: 2px solid #4F46E5; }
    .step-inactive { color: #64748B; }
    
    /* 亚马逊预览页专用 CSS */
    .amz-container { font-family: "Amazon Ember", Arial, sans-serif; background: white; color: #0F1111; padding: 20px; }
    .amz-title { font-size: 24px; line-height: 32px; font-weight: 400; color: #0F1111; }
    .amz-price { color: #B12704; font-size: 28px; }
    .amz-bullet { margin-bottom: 8px; font-size: 14px; }
    .amz-buybox { border: 1px solid #D5D9D9; border-radius: 8px; padding: 18px; }
    .amz-btn-yellow { background: #FFD814; border-color: #FCD200; border-radius: 20px; width: 100%; padding: 8px; border-style: solid; border-width: 1px; cursor: pointer; }
    .amz-btn-orange { background: #FFA41C; border-color: #FF8F00; border-radius: 20px; width: 100%; padding: 8px; border-style: solid; border-width: 1px; cursor: pointer; margin-top: 10px;}
</style>
""", unsafe_allow_html=True)

# ================= 2. 初始化服务 =================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 请先配置 Secrets！")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GOOGLE_API_KEY)

# ================= 3. 商业逻辑 (照旧) =================
def login(u, p):
    try:
        res = supabase.table("users").select("*").eq("username", u).eq("password", p).execute()
        return res.data[0] if res.data else None
    except: return None

def register(u, p):
    try:
        check = supabase.table("users").select("*").eq("username", u).execute()
        if check.data: return False, "用户已存在"
        supabase.table("users").insert({"username": u, "password": p, "balance": 0}).execute()
        return True, "注册成功"
    except: return False, "注册失败"

def use_card(u, k):
    try:
        res = supabase.table("card_keys").select("*").eq("key_code", k).eq("is_used", False).execute()
        if not res.data: return False, "无效卡密"
        card = res.data[0]
        supabase.table("card_keys").update({"is_used": True}).eq("key_code", k).execute()
        user = supabase.table("users").select("balance").eq("username", u).execute()
        supabase.table("users").update({"balance": user.data[0]["balance"] + card["amount"]}).eq("username", u).execute()
        return True, f"充值成功 +{card['amount']}"
    except: return False, "充值失败"

def deduct(u, cost):
    try:
        user = supabase.table("users").select("balance").eq("username", u).execute()
        if user.data[0]["balance"] < cost: return False
        supabase.table("users").update({"balance": user.data[0]["balance"] - cost}).eq("username", u).execute()
        return True
    except: return False

# ================= 4. AI 核心大脑 (1:1 移植自 React services/gemini.js) =================

def parse_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    # 处理可能的意外字符
    try: return json.loads(text)
    except: return None

# 1. 识别产品
def ai_identify(image):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = """
    Analyze product image. Extract info in Chinese.
    Output strictly JSON: {
        "productName": "short name",
        "material": "material",
        "features": "key features",
        "usage": "usage scenario",
        "targetAudience": "who is it for"
    }
    """
    try:
        res = model.generate_content([prompt, image])
        return parse_json(res.text)
    except: return None

# 2. 推荐类目
def ai_recommend_cat(info):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
    Based on: {json.dumps(info, ensure_ascii=False)}.
    Recommend 5 Amazon US Browse Node paths.
    Output strictly JSON: {{ "categories": ["Category 1", "Category 2"...] }}
    """
    try:
        res = model.generate_content(prompt)
        return parse_json(res.text)
    except: return None

# 3. 生成文案 (Gemini Pro)
def ai_write_listing(image, info, cat, brand):
    model = genai.GenerativeModel("gemini-1.5-pro")
    prompt = f"""
    Role: Expert Amazon Listing Optimizer for US Market.
    Context: Brand={brand}, Category={cat}, Info={json.dumps(info, ensure_ascii=False)}.
    Task:
    1. Title: Max 200 chars, SEO optimized, include Brand.
    2. Bullets: 5 points, benefits-focused.
    3. Description: HTML formatted (<br>, <b>).
    
    Output strictly JSON: {{
        "titleEn": "...", "titleCn": "...",
        "bullets": [{{"en": "...", "cn": "..."}} (5 items)],
        "descriptionEn": "HTML...", "descriptionCn": "..."
    }}
    """
    try:
        res = model.generate_content([prompt, image])
        return parse_json(res.text)
    except: return None

# 4. 视觉规划
def ai_plan_visuals(listing_data, plan_type="main"):
    model = genai.GenerativeModel("gemini-1.5-flash")
    task = "1 Main Image, 4 Secondary Images" if plan_type == "main" else "4 A+ Content Modules"
    prompt = f"""
    Plan Amazon images ({task}) for: {listing_data.get('titleEn', '')}.
    Output strictly JSON List: [{{ "label": "Main Image", "prompt": "English prompt...", "promptCn": "中文...", "type": "{plan_type}" }}, ...]
    """
    try:
        res = model.generate_content(prompt)
        return parse_json(res.text)
    except: return []

# 5. 视频脚本
def ai_video_script(title):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"Write a 15s video script prompt for AI generator for: {title}. Output text only."
    try: return model.generate_content(prompt).text
    except: return ""

# ================= 5. HTML 预览生成器 (复刻 AmazonPreview.tsx) =================
def render_amazon_preview(listing):
    html = f"""
    <div class="amz-container">
        <div style="display:flex; gap:30px; flex-wrap:wrap;">
            <!-- Left: Images Mock -->
            <div style="flex:1; min-width:300px;">
                <div style="border:1px solid #eee; padding:10px; text-align:center; height:400px; display:flex; align-items:center; justify-content:center; background:#f8f8f8; color:#999;">
                    Main Image Placeholder
                </div>
                <div style="display:flex; gap:10px; margin-top:10px; justify-content:center;">
                    <div style="width:40px; height:40px; border:1px solid #ccc;"></div>
                    <div style="width:40px; height:40px; border:1px solid #ccc;"></div>
                    <div style="width:40px; height:40px; border:1px solid #ccc;"></div>
                </div>
            </div>
            
            <!-- Center: Info -->
            <div style="flex:1.5; min-width:300px;">
                <h1 class="amz-title">{listing.get('titleEn', 'Product Title')}</h1>
                <div style="color:#007185; font-size:14px; margin-bottom:15px;">
                    ★★★★★ <span style="margin-left:5px">4,821 ratings</span>
                </div>
                <hr style="border-top: 1px solid #e7e7e7;">
                <div style="margin:15px 0;">
                    <span style="font-size:14px; vertical-align:top;">$</span>
                    <span style="font-size:28px; font-weight:500;">29</span>
                    <span style="font-size:14px; vertical-align:top;">99</span>
                </div>
                
                <div style="font-weight:bold; margin-bottom:5px;">About this item</div>
                <ul style="padding-left:20px;">
                    {''.join([f'<li class="amz-bullet">{b["en"]}</li>' for b in listing.get('bullets', [])])}
                </ul>
            </div>
            
            <!-- Right: Buy Box -->
            <div style="flex:0.5; min-width:200px;">
                <div class="amz-buybox">
                    <div style="color:#B12704; font-size:18px; font-weight:bold;">$29.99</div>
                    <div style="color:#007600; font-size:18px; margin:5px 0;">In Stock</div>
                    <button class="amz-btn-yellow">Add to Cart</button>
                    <button class="amz-btn-orange">Buy Now</button>
                    <div style="font-size:12px; color:#565959; margin-top:10px;">
                        🔒 Secure transaction
                    </div>
                </div>
            </div>
        </div>
        
        <div style="margin-top:40px;">
            <h2 style="font-size:20px; font-weight:700; color:#CC6600;">Product Description</h2>
            <div style="font-size:14px; line-height:1.5;">
                {listing.get('descriptionEn', '')}
            </div>
        </div>
    </div>
    """
    return html

# ================= 6. 主程序逻辑 =================

if "user" not in st.session_state: st.session_state["user"] = None
if "step" not in st.session_state: st.session_state["step"] = 1
# 数据仓库
if "data" not in st.session_state:
    st.session_state["data"] = {
        "image": None, "brand": "", "info": {}, "categories": [], 
        "listing": {}, "image_plan": [], "aplus_plan": [], "video": ""
    }

# --- 侧边栏 ---
with st.sidebar:
    st.title("🛍️ 亚马逊架构师")
    if not st.session_state["user"]:
        tab1, tab2 = st.tabs(["登录", "注册"])
        with tab1:
            u = st.text_input("账号", key="l1")
            p = st.text_input("密码", type="password", key="l2")
            if st.button("登录", type="primary"):
                user = login(u, p)
                if user: st.session_state["user"] = user; st.rerun()
                else: st.error("错误")
        with tab2:
            u2 = st.text_input("新账号", key="r1")
            p2 = st.text_input("新密码", type="password", key="r2")
            if st.button("注册"):
                ok, m = register(u2, p2)
                if ok: st.success(m)
                else: st.error(m)
    else:
        user = st.session_state["user"]
        try: bal = supabase.table("users").select("balance").eq("username", user["username"]).execute().data[0]["balance"]
        except: bal = 0
        
        st.markdown(f"""
        <div style="background:#EEF2FF;padding:15px;border-radius:10px;border:1px solid #C7D2FE;text-align:center;">
            <div style="color:#4F46E5;font-weight:bold;font-size:24px;">💎 {bal}</div>
            <div style="color:#6366F1;font-size:12px;">当前点数</div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("💳 充值中心"):
            k = st.text_input("卡密")
            if st.button("充值"):
                ok, m = use_card(user["username"], k)
                if ok: st.success(m); st.rerun()
                else: st.error(m)
            # 🔴 替换你的面包多链接
            st.markdown("[👉 购买点数](https://mbd.pub/)")
        
        if st.button("退出"): st.session_state["user"]=None; st.rerun()

# --- 主界面 ---

st.markdown("## 🚀 Amazon Listing Architect")

if not st.session_state["user"]:
    st.info("👋 请在左侧登录以开始。")
    st.stop()

# 步骤导航
steps = ["1.识别", "2.类目", "3.文案", "4.视觉", "5.A+页面", "6.视频", "7.预览"]
current = st.session_state["step"]
cols = st.columns(len(steps))
for i, col in enumerate(cols):
    if i + 1 == current: col.markdown(f"**🔵 {steps[i]}**")
    elif i + 1 < current: col.markdown(f"✅ {steps[i]}")
    else: col.markdown(f"<span style='color:lightgrey'>{steps[i]}</span>", unsafe_allow_html=True)
st.progress(current * (100/7))

# === Step 1: 上传与识别 ===
if current == 1:
    with st.container():
        st.markdown("### 📸 产品上传")
        col1, col2 = st.columns([1,1])
        with col1:
            f = st.file_uploader("", type=["jpg", "png"])
            if f:
                img = Image.open(f)
                st.session_state["data"]["image"] = img
                st.image(img, width=300)
        with col2:
            brand = st.text_input("品牌名称", placeholder="Anker", value=st.session_state["data"].get("brand", ""))
            st.session_state["data"]["brand"] = brand
            
            if f and brand:
                if st.button("开始 AI 识别 (免费)", type="primary"):
                    with st.spinner("AI 正在分析..."):
                        info = ai_identify(st.session_state["data"]["image"])
                        if info:
                            st.session_state["data"]["info"] = info
                            st.session_state["step"] = 2
                            st.rerun()
                        else: st.error("识别失败")

# === Step 2: 类目 ===
elif current == 2:
    st.markdown("### 🌐 类目推荐")
    info = st.session_state["data"]["info"]
    
    # 显示识别结果 (可编辑)
    c1, c2 = st.columns(2)
    with c1: st.text_input("产品名", info.get("productName"))
    with c2: st.text_input("材质", info.get("material"))
    st.text_area("卖点", info.get("features"))
    
    if not st.session_state["data"]["categories"]:
        with st.spinner("正在分析亚马逊类目..."):
            cats = ai_recommend_cat(info)
            if cats: 
                st.session_state["data"]["categories"] = cats.get("categories", [])
                st.rerun()
    
    cats = st.session_state["data"]["categories"]
    if cats:
        sel_cat = st.radio("推荐类目", cats)
        st.session_state["data"]["cat"] = sel_cat
        
        st.divider()
        if st.button("✨ 生成 Listing 文案 (扣 10 点)", type="primary"):
            if deduct(st.session_state["user"]["username"], 10):
                st.session_state["step"] = 3
                st.rerun()
            else: st.error("余额不足")

# === Step 3: 文案 ===
elif current == 3:
    st.markdown("### 📝 文案生成")
    if not st.session_state["data"]["listing"]:
        with st.spinner("Gemini Pro 正在撰写..."):
            res = ai_write_listing(
                st.session_state["data"]["image"],
                st.session_state["data"]["info"],
                st.session_state["data"]["cat"],
                st.session_state["data"]["brand"]
            )
            if res:
                st.session_state["data"]["listing"] = res
                st.rerun()
    
    lst = st.session_state["data"]["listing"]
    if lst:
        tab1, tab2, tab3 = st.tabs(["🇺🇸 标题", "✅ 五点", "📄 描述"])
        with tab1:
            st.text_area("EN", lst.get("titleEn"), height=100)
            st.caption(lst.get("titleCn"))
        with tab2:
            for b in lst.get("bullets", []):
                st.text_area("Bullet", b.get("en"), height=80)
                st.caption(b.get("cn"))
        with tab3:
            st.text_area("HTML", lst.get("descriptionEn"), height=200)
            
        if st.button("下一步：视觉规划"): st.session_state["step"] = 4; st.rerun()

# === Step 4: 图片规划 ===
elif current == 4:
    st.markdown("### 🎨 主图与副图规划")
    if not st.session_state["data"]["image_plan"]:
        with st.spinner("正在规划..."):
            res = ai_plan_visuals(st.session_state["data"]["listing"], "main")
            st.session_state["data"]["image_plan"] = res
            st.rerun()
            
    for p in st.session_state["data"]["image_plan"]:
        with st.expander(f"📸 {p.get('label')}"):
            st.code(p.get("prompt"))
            if st.button("生成此图 (扣2点)", key=p.get('prompt')):
                if deduct(st.session_state["user"]["username"], 2):
                    st.image("https://via.placeholder.com/400?text=AI+Image", caption="模拟生成结果")
                else: st.error("余额不足")
                
    if st.button("下一步：A+页面"): st.session_state["step"] = 5; st.rerun()

# === Step 5: A+ 页面 ===
elif current == 5:
    st.markdown("### 📄 A+ 页面内容规划")
    if not st.session_state["data"]["aplus_plan"]:
        with st.spinner("正在规划 A+ 模块..."):
            res = ai_plan_visuals(st.session_state["data"]["listing"], "aplus")
            st.session_state["data"]["aplus_plan"] = res
            st.rerun()
            
    for p in st.session_state["data"]["aplus_plan"]:
        with st.expander(f"🖼️ {p.get('label')}"):
            st.code(p.get("prompt"))
            
    if st.button("下一步：视频脚本"): st.session_state["step"] = 6; st.rerun()

# === Step 6: 视频 ===
elif current == 6:
    st.markdown("### 🎥 视频脚本")
    if not st.session_state["data"]["video"]:
        with st.spinner("生成视频脚本..."):
            res = ai_video_script(st.session_state["data"]["listing"].get("titleEn"))
            st.session_state["data"]["video"] = res
            st.rerun()
            
    st.text_area("Video Prompt", st.session_state["data"]["video"], height=150)
    if st.button("下一步：最终预览"): st.session_state["step"] = 7; st.rerun()

# === Step 7: 预览 ===
elif current == 7:
    st.markdown("### 👁️ 亚马逊前台预览")
    
    # 渲染 React 复刻版预览页
    html_preview = render_amazon_preview(st.session_state["data"]["listing"])
    st.markdown(html_preview, unsafe_allow_html=True)
    
    st.divider()
    if st.button("📦 打包下载所有素材"):
        mem_zip = io.BytesIO()
        with zipfile.ZipFile(mem_zip, mode="w") as zf:
            l = st.session_state["data"]["listing"]
            txt = f"TITLE: {l.get('titleEn')}\n\nBULLETS:\n" + "\n".join([b['en'] for b in l.get('bullets', [])])
            zf.writestr("listing.txt", txt)
        st.download_button("点击下载 ZIP", mem_zip.getvalue(), "amazon_assets.zip", "application/zip")
        
    if st.button("🔄 开始新项目"):
        st.session_state["step"] = 1
        st.session_state["data"] = {"image": None, "brand": "", "info": {}, "categories": [], "listing": {}, "image_plan": [], "aplus_plan": [], "video": ""}
        st.rerun()
