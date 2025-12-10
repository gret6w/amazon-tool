import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image
import json
import time

# ================= 1. 深度 UI 定制 (核心美化) =================
st.set_page_config(
    page_title="Amazon Listing Architect",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入 CSS：强制覆盖 Streamlit 样式，复刻 React 版的视觉风格
st.markdown("""
<style>
    /* 1. 全局字体与背景 (仿 Stripe/Amazon) */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    .stApp {
        background-color: #F3F4F6; /* 高级灰背景 */
        font-family: 'Inter', sans-serif;
    }
    
    /* 2. 隐藏 Streamlit 原生丑元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 3. 卡片式容器 (仿 React 组件) */
    .element-container, .stMarkdown {
        background-color: transparent;
    }
    div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] > div[data-testid="stVerticalBlock"] {
        background-color: white;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #E5E7EB;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    
    /* 4. 按钮美化 (亚马逊橙 & 谷歌蓝) */
    div.stButton > button {
        border-radius: 8px;
        font-weight: 600;
        border: none;
        padding: 0.5rem 1rem;
        transition: all 0.2s;
    }
    /* 主操作按钮 */
    div.stButton > button[kind="primary"] {
        background-color: #4F46E5; /* Indigo-600 */
        color: white;
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2);
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #4338CA;
        transform: translateY(-1px);
    }
    
    /* 5. 侧边栏美化 */
    section[data-testid="stSidebar"] {
        background-color: white;
        border-right: 1px solid #E5E7EB;
    }
    
    /* 6. 进度条美化 */
    .stProgress > div > div > div > bg-2b {
        background-color: #4F46E5;
    }
    
    /* 7. 标题样式 */
    h1, h2, h3 {
        color: #111827;
        font-weight: 700;
        letter-spacing: -0.025em;
    }
    
    /* 自定义顶栏 */
    .top-nav {
        background: #111827;
        padding: 1rem 2rem;
        color: white;
        border-radius: 0 0 12px 12px;
        margin: -4rem -4rem 2rem -4rem; /* 抵消 padding */
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
</style>
""", unsafe_allow_html=True)

# ================= 2. 初始化服务 =================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 请先配置 Secrets")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GOOGLE_API_KEY)

# ================= 3. 商业逻辑 (保持不变) =================
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

# ================= 4. AI 逻辑 (JSON 解析) =================
def parse_json(text):
    try: return json.loads(text.replace("```json", "").replace("```", "").strip())
    except: return None

def ai_process(prompt, image=None, model="flash"):
    m = genai.GenerativeModel(f"gemini-1.5-{model}")
    try:
        content = [prompt, image] if image else [prompt]
        return m.generate_content(content).text
    except Exception as e: return f"Error: {e}"

# ================= 5. 界面渲染 (高度模仿 React) =================

if "user" not in st.session_state: st.session_state["user"] = None
if "step" not in st.session_state: st.session_state["step"] = 1
if "data" not in st.session_state: st.session_state["data"] = {"image": None, "info": None, "listing": None}

# --- 侧边栏 (极简风格) ---
with st.sidebar:
    st.markdown("### 🛍️ Amazon Architect")
    
    if not st.session_state["user"]:
        st.info("请先登录")
        tab1, tab2 = st.tabs(["登录", "注册"])
        with tab1:
            u = st.text_input("账号", key="l1")
            p = st.text_input("密码", type="password", key="l2")
            if st.button("进入系统", type="primary"):
                user = login(u, p)
                if user: st.session_state["user"] = user; st.rerun()
                else: st.error("错误")
        with tab2:
            u2 = st.text_input("新账号", key="r1")
            p2 = st.text_input("新密码", type="password", key="r2")
            if st.button("创建账户"):
                ok, m = register(u2, p2)
                if ok: st.success(m)
    else:
        user = st.session_state["user"]
        try: bal = supabase.table("users").select("balance").eq("username", user["username"]).execute().data[0]["balance"]
        except: bal = 0
        
        # 余额卡片
        st.markdown(f"""
        <div style="background:linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); padding:20px; border-radius:12px; color:white; margin-bottom:20px; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.3);">
            <div style="font-size:12px; opacity:0.8;">可用余额</div>
            <div style="font-size:28px; font-weight:700;">💎 {bal}</div>
            <div style="font-size:12px; margin-top:5px;">用户: {user['username']}</div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("💳 充值 / Recharge"):
            k = st.text_input("输入卡密")
            if st.button("兑换"):
                ok, m = use_card(user["username"], k)
                if ok: st.success(m); st.rerun()
                else: st.error(m)
            st.markdown("[👉 购买卡密](https://mbd.pub/)") # 🔴 替换你的链接
            
        if st.button("退出"): st.session_state["user"]=None; st.rerun()

# --- 主界面 ---

if not st.session_state["user"]:
    # 落地页
    st.markdown("""
    <div style="text-align:center; padding: 4rem 0;">
        <h1 style="font-size: 3rem; margin-bottom: 1rem;">打造完美的亚马逊 Listing</h1>
        <p style="font-size: 1.2rem; color: #6B7280; margin-bottom: 2rem;">AI 驱动 ・ 视觉规划 ・ 销量倍增</p>
        <div style="background: white; padding: 2rem; border-radius: 1rem; display: inline-block; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
            👈 请在左侧登录以开始使用
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# 步骤导航 (仿 React 的 StepIndicator)
current = st.session_state["step"]
st.markdown(f"""
<div style="display:flex; justify-content:space-between; margin-bottom:20px; padding:0 10px;">
    <div style="color:{'#4F46E5' if current==1 else '#9CA3AF'}; font-weight:{'bold' if current==1 else 'normal'}">1. 上传与识别</div>
    <div style="color:{'#4F46E5' if current==2 else '#9CA3AF'}; font-weight:{'bold' if current==2 else 'normal'}">2. 类目选择</div>
    <div style="color:{'#4F46E5' if current==3 else '#9CA3AF'}; font-weight:{'bold' if current==3 else 'normal'}">3. 文案生成</div>
    <div style="color:{'#4F46E5' if current==4 else '#9CA3AF'}; font-weight:{'bold' if current==4 else 'normal'}">4. 视觉规划</div>
</div>
<div style="height:4px; background:#E5E7EB; border-radius:2px; margin-bottom:30px;">
    <div style="height:100%; width:{current/4*100}%; background:#4F46E5; border-radius:2px; transition: width 0.3s;"></div>
</div>
""", unsafe_allow_html=True)

# === Step 1 ===
if current == 1:
    st.markdown("### 📸 上传产品图")
    # 使用 Container 模拟卡片
    with st.container():
        col1, col2 = st.columns([1, 1.5])
        with col1:
            f = st.file_uploader("", type=["jpg", "png"])
            if f:
                img = Image.open(f)
                st.session_state["data"]["image"] = img
                st.image(img, use_column_width=True)
        with col2:
            st.info("💡 提示：上传清晰的白底图或场景图，AI 将自动识别卖点。")
            brand = st.text_input("品牌名称 (Brand)", placeholder="例如: Anker")
            st.session_state["data"]["brand"] = brand
            
            if f and brand:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("开始 AI 识别 (免费)", type="primary"):
                    with st.spinner("AI 正在分析..."):
                        prompt = "Analyze product image. Output strictly JSON: {productName, material, features, usage, targetAudience} in Chinese."
                        res = ai_process(prompt, img)
                        info = parse_json(res)
                        if info:
                            st.session_state["data"]["info"] = info
                            st.session_state["step"] = 2
                            st.rerun()
                        else: st.error("识别失败")

# === Step 2 ===
elif current == 2:
    st.markdown("### 🌐 确认信息与类目")
    info = st.session_state["data"]["info"]
    
    with st.container():
        c1, c2 = st.columns(2)
        with c1: st.text_input("产品名", info.get("productName"))
        with c2: st.text_input("材质", info.get("material"))
        st.text_area("AI 提取的卖点", info.get("features"), height=100)
        
        st.markdown("#### 推荐类目")
        if not st.session_state["data"].get("categories"):
            with st.spinner("正在分析类目..."):
                prompt = f"Recommend 5 Amazon US Browse Nodes based on: {json.dumps(info, ensure_ascii=False)}. Output strictly JSON: {{categories: []}}"
                res = ai_process(prompt)
                cats = parse_json(res)
                st.session_state["data"]["categories"] = cats.get("categories", [])
                st.rerun()
        
        cats = st.session_state["data"].get("categories", [])
        if cats:
            sel = st.radio("", cats)
            st.session_state["data"]["cat"] = sel
            
            st.divider()
            col_l, col_r = st.columns([3, 1])
            with col_l:
                st.caption("即将生成：SEO标题 + 五点描述 + HTML详情")
            with col_r:
                if st.button("生成文案 (扣10点)", type="primary"):
                    if deduct(st.session_state["user"]["username"], 10):
                        st.session_state["step"] = 3
                        st.rerun()
                    else: st.error("余额不足")

# === Step 3 ===
elif current == 3:
    st.markdown("### 📝 文案结果")
    
    if not st.session_state["data"]["listing"]:
        with st.spinner("Gemini Pro 正在撰写..."):
            info = st.session_state["data"]["info"]
            prompt = f"""
            Role: Expert Amazon Listing Copywriter.
            Info: {json.dumps(info, ensure_ascii=False)}.
            Task: Write Title, 5 Bullets, HTML Description.
            Output strictly JSON: {{titleEn, titleCn, bullets: [{{en, cn}}], descriptionEn}}
            """
            res = ai_process(prompt, st.session_state["data"]["image"], "pro")
            listing = parse_json(res)
            st.session_state["data"]["listing"] = listing
            st.rerun()
            
    lst = st.session_state["data"]["listing"]
    if lst:
        with st.container():
            t1, t2, t3 = st.tabs(["🇺🇸 标题", "✅ 五点", "📄 详情"])
            with t1:
                st.text_area("English", lst.get("titleEn"), height=80)
                st.info(lst.get("titleCn"))
            with t2:
                for b in lst.get("bullets", []):
                    st.text_area("Bullet", b.get("en"), height=80)
            with t3:
                st.code(lst.get("descriptionEn"), language="html")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("下一步：视觉规划", type="primary"):
            st.session_state["step"] = 4
            st.rerun()

# === Step 4 ===
elif current == 4:
    st.markdown("### 🎨 视觉规划")
    st.success("🎉 文案已生成！视觉规划功能正在开发中...")
    if st.button("🔄 开始新项目"):
        st.session_state["step"] = 1
        st.session_state["data"] = {"image": None, "info": None, "listing": None}
        st.rerun()
