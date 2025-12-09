import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
from PIL import Image

# --- 1. 配置与初始化 (从 Secrets 获取密钥) ---
# 注意：千万不要把密钥直接写在代码里，要去 Streamlit 后台配置！
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("请先在 Streamlit 后台配置 Secrets！")
    st.stop()

# 连接数据库和AI
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GOOGLE_API_KEY)

# --- 2. 辅助函数 ---

def login(username, password):
    """登录检查"""
    try:
        response = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()
        if len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"登录出错: {e}")
        return None

def register(username, password):
    """注册新用户"""
    try:
        # 检查是否已存在
        check = supabase.table("users").select("*").eq("username", username).execute()
        if len(check.data) > 0:
            return False, "用户名已存在"
        # 插入新用户 (余额默认为 0)
        supabase.table("users").insert({"username": username, "password": password, "balance": 0}).execute()
        return True, "注册成功，请登录"
    except Exception as e:
        return False, f"注册出错: {e}"

def recharge(username, card_key):
    """充值功能"""
    try:
        # 1. 查询卡密
        response = supabase.table("card_keys").select("*").eq("key_code", card_key).eq("is_used", False).execute()
        if len(response.data) == 0:
            return False, "卡密无效或已被使用"
        
        card_data = response.data[0]
        amount = card_data["amount"]
        
        # 2. 标记卡密为已用
        supabase.table("card_keys").update({"is_used": True}).eq("key_code", card_key).execute()
        
        # 3. 给用户加余额 (先查当前余额)
        user_res = supabase.table("users").select("balance").eq("username", username).execute()
        current_balance = user_res.data[0]["balance"]
        new_balance = current_balance + amount
        
        supabase.table("users").update({"balance": new_balance}).eq("username", username).execute()
        
        return True, f"充值成功！增加 {amount} 点"
    except Exception as e:
        return False, f"充值失败: {e}"

def deduct_points(username, cost=1):
    """扣费功能"""
    try:
        user_res = supabase.table("users").select("balance").eq("username", username).execute()
        current_balance = user_res.data[0]["balance"]
        if current_balance < cost:
            return False
        
        # 扣费
        supabase.table("users").update({"balance": current_balance - cost}).eq("username", username).execute()
        return True
    except:
        return False

def generate_desc(image):
    """调用谷歌AI生成描述"""
    model = genai.GenerativeModel('gemini-1.5-flash') # 使用最新的快速模型
    prompt = """
    你是一个专业的亚马逊Listing文案专家。请仔细观察这张产品图片，用地道的英语生成一段 Product Visual Description。
    要求：
    1. 重点描述材质、颜色、形状、纹理和工艺细节。
    2. 使用母语级别的形容词。
    3. 不要包含虚假宣传。
    4. 仅输出英文描述段落，不要其他废话。
    """
    response = model.generate_content([prompt, image])
    return response.text

# --- 3. 页面界面逻辑 ---

st.set_page_config(page_title="Amazon视觉描述神器", layout="wide")

# 初始化 Session State
if "user" not in st.session_state:
    st.session_state["user"] = None

# === 侧边栏：登录/注册/充值 ===
with st.sidebar:
    st.title("🔐 账号管理")
    
    if st.session_state["user"] is None:
        tab1, tab2 = st.tabs(["登录", "注册"])
        with tab1:
            l_user = st.text_input("用户名", key="l_u")
            l_pass = st.text_input("密码", type="password", key="l_p")
            if st.button("登录"):
                user_info = login(l_user, l_pass)
                if user_info:
                    st.session_state["user"] = user_info
                    st.success("登录成功！")
                    st.rerun()
                else:
                    st.error("账号或密码错误")
        with tab2:
            r_user = st.text_input("新用户名", key="r_u")
            r_pass = st.text_input("新密码", type="password", key="r_p")
            if st.button("注册"):
                success, msg = register(r_user, r_pass)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    else:
        # 已登录状态
        username = st.session_state["user"]["username"]
        # 实时查询余额
        try:
            balance_res = supabase.table("users").select("balance").eq("username", username).execute()
            balance = balance_res.data[0]["balance"]
        except:
            balance = 0
            
        st.info(f"👤 用户: {username}")
        st.metric(label="💰 当前点数", value=balance)
        
        if st.button("退出登录"):
            st.session_state["user"] = None
            st.rerun()
            
        st.divider()
        st.subheader("💎 充值中心")
        key_input = st.text_input("请输入充值卡密")
        if st.button("立即充值"):
            success, msg = recharge(username, key_input)
            if success:
                st.balloons()
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
        
        st.markdown("[👉 点击购买点数 (9.9元/100点)](https://mbd.pub/o/你的面包多链接)") # 这里记得换成你的面包多链接

# === 主界面：功能区 ===
st.title("🚀 亚马逊视觉描述生成器")
st.markdown("上传产品图片，AI自动识别细节并生成地道英文描述。**每次生成扣除 1 点。**")

if st.session_state["user"]:
    uploaded_file = st.file_uploader("请上传产品图片...", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='已上传图片', width=300)
        
        if st.button("✨ 开始生成描述 (消耗1点)"):
            username = st.session_state["user"]["username"]
            
            # 1. 扣费检查
            if deduct_points(username, 1):
                with st.spinner('AI 正在观察图片细节...'):
                    try:
                        # 2. 调用AI
                        description = generate_desc(image)
                        st.success("✅ 生成成功！")
                        st.text_area("生成的英文描述 (直接复制)：", value=description, height=200)
                        st.info("💡 建议：请结合你的 SEO 关键词，将这段描述作为 Listing 的 Feature Bullets 使用。")
                        st.rerun() # 刷新页面更新余额
                    except Exception as e:
                        st.error(f"生成失败，请重试: {e}")
            else:
                st.error("余额不足！请在左侧侧边栏充值。")
else:
    st.warning("👈 请先在左侧侧边栏 登录 或 注册 后使用。")
