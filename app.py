import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image
import json
import io
import zipfile
import time

# ================= 1. 系统配置与美化 =================
st.set_page_config(
    page_title="Amazon Listing Architect",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入 CSS (复刻 React 版的 Slate/Indigo 风格)
st.markdown("""
<style>
    .stApp { background-color: #F8FAFC; }
    .css-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
    /* 进度条样式 */
    .stProgress > div > div > div > bg-2b { background-color: #4F46E5; }
    h1, h2, h3 { color: #1E293B; font-family: 'Inter', sans-serif; }
    /* 侧边栏 */
    [data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E2E8F0; }
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

# ================= 3. 商业逻辑 (账户/充值) =================
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

# ================= 4. AI 核心大脑 (移植自 React 代码) =================

def parse_json(text):
    """清洗 AI 返回的 JSON"""
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except: return None

def ai_identify(image):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = """
    Analyze product image. Extract info in Chinese (or English where appropriate).
    Output JSON: {
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

def ai_recommend_cat(info):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
    Based on: {json.dumps(info, ensure_ascii=False)}.
    Recommend 5 Amazon US Browse Nodes.
    Output JSON: {{ "categories": ["Category 1", "Category 2"...] }}
    """
    try:
        res = model.generate_content(prompt)
        return parse_json(res.text)
    except: return None

def ai_write_listing(image, info, cat, brand):
    model = genai.GenerativeModel("gemini-1.5-pro")
    prompt = f"""
    Role: Expert Amazon Listing Copywriter.
    Context: Brand={brand}, Category={cat}, Info={json.dumps(info, ensure_ascii=False)}.
    Task: Write SEO optimized listing for US Market.
    Output JSON: {{
        "titleEn": "...", "titleCn": "...",
        "bullets": [{{"en": "...", "cn": "..."}} (5 items)],
        "descriptionEn": "HTML formatted...", "descriptionCn": "..."
    }}
    """
    try:
        res = model.generate_content([prompt, image])
        return parse_json(res.text)
    except: return None

def ai_plan_visuals(title):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
    Plan Amazon images for: {title}.
    1 Main Image, 4 Secondary Images.
    Output JSON List: [{{ "label": "Main Image", "prompt": "English prompt...", "type": "main" }}, ...]
    """
    try:
        res = model.generate_content(prompt)
        return parse_json(res.text)
    except: return []

def ai_video_script(title):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"Write a 15s video script prompt for AI video generator for product: {title}. Output simple text."
    try:
        res = model.generate_content(prompt)
        return res.text
    except: return ""

# ================= 5. 界面逻辑 (Streamlit UI) =================

if "user" not in st.session_state: st.session_state["user"] = None
if "step" not in st.session_state: st.session_state["step"] = 1
# 数据仓库
if "data" not in st.session_state:
    st.session_state["data"] = {
        "image": None, "info": {}, "categories": [], "listing": {}, "visuals": [], "video": ""
    }

# --- 侧边栏：账户体系 ---
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
        st.caption(f"当前用户: {user['username']}")
        
        with st.expander("💳 充值中心"):
            k = st.text_input("卡密")
            if st.button("充值"):
                ok, m = use_card(user["username"], k)
                if ok: st.success(m); st.rerun()
                else: st.error(m)
            st.markdown("[👉 购买卡密](https://mbd.pub/)") # 🔴 替换你的链接
        
        if st.button("退出"): st.session_state["user"]=None; st.rerun()

# --- 主界面 ---

st.markdown("## 🚀 Amazon Listing Architect")

if not st.session_state["user"]:
    st.info("👋 请先在左侧登录。")
    st.stop()

# 步骤条
steps = ["1.识别", "2.类目", "3.文案", "4.视觉", "5.下载"]
current = st.session_state["step"]
cols = st.columns(5)
for i, col in enumerate(cols):
    if i + 1 == current:
        col.markdown(f"**🔵 {steps[i]}**")
    elif i + 1 < current:
        col.markdown(f"✅ {steps[i]}")
    else:
        col.markdown(f"<span style='color:grey'>{steps[i]}</span>", unsafe_allow_html=True)
st.progress(current * 20)

# === Step 1: 识别 ===
if current == 1:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 📸 上传产品")
        f = st.file_uploader("", type=["jpg", "png"])
        if f:
            img = Image.open(f)
            st.session_state["data"]["image"] = img
            st.image(img, width=300)
    with col2:
        st.markdown("### 🏷️ 基础信息")
        brand = st.text_input("品牌 (Brand)", placeholder="例如: Anker")
        st.session_state["data"]["brand"] = brand
        
        if f and brand:
            if st.button("开始识别 (免费)", type="primary"):
                with st.spinner("AI 正在分析..."):
                    info = ai_identify(st.session_state["data"]["image"])
                    if info:
                        st.session_state["data"]["info"] = info
                        st.session_state["step"] = 2
                        st.rerun()
                    else: st.error("识别失败")

# === Step 2: 类目 ===
elif current == 2:
    st.markdown("### 🌐 确认信息与类目")
    info = st.session_state["data"]["info"]
    
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("产品名称", value=info.get("productName", ""))
        st.text_input("材质", value=info.get("material", ""))
    with col2:
        st.text_area("卖点", value=info.get("features", ""))
    
    if not st.session_state["data"]["categories"]:
        with st.spinner("正在推荐类目..."):
            cats = ai_recommend_cat(info)
            if cats: 
                st.session_state["data"]["categories"] = cats.get("categories", [])
                st.rerun()
    
    cats = st.session_state["data"]["categories"]
    if cats:
        sel_cat = st.radio("推荐类目", cats)
        st.session_state["data"]["cat"] = sel_cat
        
        st.divider()
        st.info("即将生成：SEO标题 + 五点描述 + HTML详情")
        if st.button("✨ 生成 Listing (扣 10 点)", type="primary"):
            if deduct(st.session_state["user"]["username"], 10):
                st.session_state["step"] = 3
                st.rerun()
            else: st.error("余额不足")

# === Step 3: 文案 ===
elif current == 3:
    st.markdown("### 📝 文案生成结果")
    
    if not st.session_state["data"]["listing"]:
        with st.spinner("Gemini Pro 正在撰写文案..."):
            res = ai_write_listing(
                st.session_state["data"]["image"],
                st.session_state["data"]["info"],
                st.session_state["data"]["cat"],
                st.session_state["data"]["brand"]
            )
            if res:
                st.session_state["data"]["listing"] = res
                st.rerun()
    
    listing = st.session_state["data"]["listing"]
    if listing:
        tab1, tab2, tab3 = st.tabs(["🇺🇸 标题", "✅ 五点", "📄 详情"])
        with tab1:
            st.text_area("English Title", listing.get("titleEn", ""))
            st.caption(listing.get("titleCn", ""))
        with tab2:
            for b in listing.get("bullets", []):
                st.text_area("Bullet", b.get("en", ""), height=100)
                st.caption(b.get("cn", ""))
        with tab3:
            st.code(listing.get("descriptionEn", ""), language="html")
            
        if st.button("下一步：视觉规划"):
            st.session_state["step"] = 4
            st.rerun()

# === Step 4: 视觉 ===
elif current == 4:
    st.markdown("### 🎨 视觉与视频规划")
    
    if not st.session_state["data"]["visuals"]:
        with st.spinner("正在规划图片和视频脚本..."):
            vis = ai_plan_visuals(st.session_state["data"]["listing"].get("titleEn", ""))
            vid = ai_video_script(st.session_state["data"]["listing"].get("titleEn", ""))
            st.session_state["data"]["visuals"] = vis
            st.session_state["data"]["video"] = vid
            st.rerun()
            
    visuals = st.session_state["data"]["visuals"]
    for v in visuals:
        with st.expander(f"📸 {v.get('label')}"):
            st.code(v.get("prompt"))
            if st.button("生成预览图 (扣2点)", key=v.get("label")):
                if deduct(st.session_state["user"]["username"], 2):
                    st.image("https://via.placeholder.com/400x400?text=AI+Generated+Image", caption="模拟生成结果")
                else: st.error("余额不足")
    
    st.divider()
    st.markdown("#### 🎥 视频脚本")
    st.text_area("Video Prompt", st.session_state["data"]["video"])
    
    if st.button("完成预览"):
        st.session_state["step"] = 5
        st.rerun()

# === Step 5: 下载 ===
elif current == 5:
    st.success("🎉 所有内容已生成完毕！")
    
    # 打包下载逻辑
    if st.button("📦 打包下载所有素材"):
        # 创建 ZIP
        mem_zip = io.BytesIO()
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. 写入文案
            listing = st.session_state["data"]["listing"]
            text_content = f"""
BRAND: {st.session_state['data']['brand']}
TITLE: {listing.get('titleEn')}
BULLETS:
{json.dumps(listing.get('bullets'), indent=2)}
DESCRIPTION:
{listing.get('descriptionEn')}
            """
            zf.writestr("listing.txt", text_content)
            
            # 2. 写入视觉提示词
            visuals = st.session_state["data"]["visuals"]
            zf.writestr("image_prompts.json", json.dumps(visuals, indent=2))
            
        st.download_button(
            label="点击下载 ZIP",
            data=mem_zip.getvalue(),
            file_name="amazon_assets.zip",
            mime="application/zip"
        )
    
    if st.button("🔄 开始新产品"):
        st.session_state["step"] = 1
        st.session_state["data"] = {"image": None, "info": {}, "categories": [], "listing": {}, "visuals": [], "video": ""}
        st.rerun()
