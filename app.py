import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image
import json
import io
import zipfile

# ================= 1. 深度美化配置 (整容核心) =================
st.set_page_config(
    page_title="Amazon Listing Architect",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed" # 默认收起侧边栏，让主界面更宽
)

# 注入 CSS: 强制覆盖 Streamlit 原生样式，模仿 Google AI Studio 风格
st.markdown("""
<style>
    /* 全局字体与背景 - 模仿 Google Material Design */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    
    .stApp {
        background-color: #F0F4F9; /* 谷歌浅灰背景 */
        font-family: 'Inter', sans-serif;
    }
    
    /* 隐藏顶部红线和菜单 */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 卡片容器风格 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 95% !important;
    }
    
    /* 自定义卡片 */
    .st-card {
        background: white;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        border: 1px solid #E1E3E1;
    }
    
    /* 按钮美化 - 谷歌蓝 */
    div.stButton > button {
        border-radius: 20px;
        background-color: #0B57D0;
        color: white;
        border: none;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.2s;
    }
    div.stButton > button:hover {
        background-color: #0842A0;
        box-shadow: 0 4px 8px rgba(11, 87, 208, 0.3);
    }
    div.stButton > button:active {
        transform: scale(0.98);
    }
    
    /* 输入框美化 */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 1px solid #C4C7C5;
    }
    
    /* 侧边栏美化 */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E1E3E1;
    }
    
    /* 标题样式 */
    h1, h2, h3 {
        color: #1F1F1F;
        font-weight: 600;
    }
    
    /* 自定义进度样式 */
    .step-box {
        background: white;
        padding: 10px 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid #E1E3E1;
    }
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

# ================= 3. 核心功能函数 (逻辑层) =================
# ... (保持原有的商业逻辑不变，确保稳定) ...
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

# --- AI 函数 ---
def parse_json(text):
    try: return json.loads(text.replace("```json", "").replace("```", "").strip())
    except: return None

def ai_process(prompt, image=None, model_type="flash"):
    model_name = "gemini-1.5-pro" if model_type == "pro" else "gemini-1.5-flash"
    model = genai.GenerativeModel(model_name)
    try:
        content = [prompt, image] if image else [prompt]
        res = model.generate_content(content)
        return res.text
    except Exception as e: return f"Error: {e}"

# ================= 4. 界面渲染 (UI层) =================

if "user" not in st.session_state: st.session_state["user"] = None
if "data" not in st.session_state: 
    st.session_state["data"] = {"image": None, "info": None, "listing": None, "visuals": None}

# --- 侧边栏：极简账户管理 ---
with st.sidebar:
    st.markdown("### 👤 账户")
    if not st.session_state["user"]:
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
                else: st.error(m)
    else:
        user = st.session_state["user"]
        # 实时余额
        try: bal = supabase.table("users").select("balance").eq("username", user["username"]).execute().data[0]["balance"]
        except: bal = 0
        
        st.info(f"用户: {user['username']}")
        st.markdown(f"<h1 style='color:#0B57D0; margin:0;'>💎 {bal}</h1>", unsafe_allow_html=True)
        st.caption("可用点数")
        
        with st.expander("充值"):
            k = st.text_input("卡密")
            if st.button("兑换"):
                ok, m = use_card(user["username"], k)
                if ok: st.success(m); st.rerun()
                else: st.error(m)
            st.markdown("[👉 购买卡密](https://mbd.pub/)") # 替换链接
            
        if st.button("退出"): st.session_state["user"]=None; st.rerun()

# --- 主内容区 ---

# 顶部导航栏 (仿 SaaS)
st.markdown("""
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
    <div style="font-size:24px; font-weight:bold; color:#1F1F1F;">✨ Amazon Listing Architect</div>
    <div style="color:#0B57D0; font-weight:600;">Pro Version 2.0</div>
</div>
""", unsafe_allow_html=True)

if not st.session_state["user"]:
    st.warning("请在左侧侧边栏登录以开始工作。")
    st.stop()

# 核心工作区 - 采用 "Tab" 布局代替纯进度条，更像软件
tabs = st.tabs(["1. 产品识别", "2. 文案生成", "3. 视觉规划", "4. 导出结果"])

# === Tab 1: 识别 (左图右文布局 - 模仿 Google AI Studio) ===
with tabs[0]:
    col1, col2 = st.columns([1, 1.5]) # 左窄右宽
    
    with col1:
        st.markdown("#### 📸 输入区")
        uploaded_file = st.file_uploader("上传产品图片", type=["jpg", "png"])
        if uploaded_file:
            image = Image.open(uploaded_file)
            st.session_state["data"]["image"] = image
            st.image(image, use_column_width=True, caption="预览")
            
    with col2:
        st.markdown("#### 🧠 AI 分析区")
        if uploaded_file:
            brand = st.text_input("品牌名称 (Brand)", placeholder="例如: Anker")
            st.session_state["data"]["brand"] = brand
            
            # 使用 expander 隐藏复杂的 Prompt，保持界面干净
            with st.expander("查看/修改 System Instructions"):
                prompt_identify = st.text_area("提示词", value="Analyze product image. Extract info in Chinese: productName, material, features, usage.", height=100)
            
            if st.button("开始识别 (免费)", type="primary"):
                with st.spinner("Gemini 正在观察图片..."):
                    res = ai_process(prompt_identify, image)
                    # 尝试解析 JSON，如果失败则直接显示文本
                    json_res = parse_json(res)
                    if json_res:
                        st.session_state["data"]["info"] = json_res
                        st.json(json_res)
                    else:
                        st.session_state["data"]["info"] = {"raw": res}
                        st.write(res)
                    st.success("识别完成！请切换到 '文案生成' 标签页。")

# === Tab 2: 文案 (高级参数控制) ===
with tabs[1]:
    if not st.session_state["data"].get("info"):
        st.info("请先在第一步上传并识别产品。")
    else:
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.markdown("#### 📝 生成结果预览")
            if st.session_state["data"]["listing"]:
                l = st.session_state["data"]["listing"]
                # 尝试如果是JSON就漂亮显示，否则直接显示文本
                if isinstance(l, dict):
                    st.text_input("Title", l.get("titleEn", ""))
                    st.text_area("Bullets", str(l.get("bullets", "")))
                    st.text_area("Description", l.get("descriptionEn", ""))
                else:
                    st.write(l)
            else:
                st.markdown("*等待生成...*")
                
        with c2:
            st.markdown("#### ⚙️ 参数配置")
            temp = st.slider("创意度 (Temperature)", 0.0, 1.0, 0.7)
            
            st.markdown("#### 💰 操作")
            st.write("预计消耗: **10 点**")
            
            if st.button("✨ 生成 Listing", type="primary"):
                if deduct(st.session_state["user"]["username"], 10):
                    prompt_listing = f"""
                    Role: Expert Amazon Listing Copywriter.
                    Brand: {st.session_state['data']['brand']}
                    Info: {st.session_state['data']['info']}
                    Task: Write Title, 5 Bullets, HTML Description.
                    Output JSON: {{titleEn, titleCn, bullets, descriptionEn}}
                    """
                    with st.spinner("正在撰写文案..."):
                        res = ai_process(prompt_listing, st.session_state["data"]["image"], "pro")
                        st.session_state["data"]["listing"] = parse_json(res) or res
                        st.rerun()
                else:
                    st.error("余额不足")

# === Tab 3: 视觉 ===
with tabs[2]:
    if not st.session_state["data"]["listing"]:
        st.info("请先生成文案。")
    else:
        st.markdown("#### 🎨 AI 视觉指导")
        if st.button("生成拍摄需求 (扣2点)"):
            if deduct(st.session_state["user"]["username"], 2):
                prompt_vis = f"Plan 5 Amazon images for: {st.session_state['data']['listing']}. Output JSON list."
                with st.spinner("规划中..."):
                    res = ai_process(prompt_vis)
                    st.session_state["data"]["visuals"] = parse_json(res) or res
                    st.rerun()
            else: st.error("余额不足")
            
        if st.session_state["data"]["visuals"]:
            st.json(st.session_state["data"]["visuals"])

# === Tab 4: 导出 ===
with tabs[3]:
    st.markdown("#### 📦 下载资源包")
    if st.session_state["data"]["listing"]:
        # 简单的打包下载
        txt_data = str(st.session_state["data"]["listing"])
        st.download_button("下载 Listing (.txt)", txt_data, "listing.txt")
    else:
        st.caption("暂无内容可下载")
