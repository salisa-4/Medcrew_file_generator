import os
import json
import logging
import re
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# --- FLASK WEB SERVER (For Render 24/7 Keep-Alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Med Crew Bot is Running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- CONFIGURATION ---
ADMIN_PASSWORD = "MedCrew2026#"  # 🔐 كلمة سر الأدمن
DB_FILE = "database.json"
BOT_TOKEN = "8656830043:AAE_v7dSxy_JWS_VGUO7hKqhP21NBLi-8xc"  # ⚠️ ضعي التوكن هنا

# --- DATABASE SETUP ---
def load_db():
    # يبدأ الكود بقاعدة بيانات فارغة للمواد، ولونين افتراضيين يتم تغييرهم من التيليجرام
    if not os.path.exists(DB_FILE):
        default_db = {
            "subjects": {},
            "colors": {
                "primary": "#1A237E",   # اللون الأساسي الافتراضي
                "secondary": "#212121"  # اللون الفرعي الافتراضي
            }
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(default_db, f, ensure_ascii=False, indent=4)
        return default_db
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- CONVERSATION STATES FOR ADMIN ---
AUTH, WAIT_ACTION, WAIT_SUB_NAME, WAIT_SUB_BG, WAIT_PRI_COLOR, WAIT_SEC_COLOR = range(6)

# --- HELPER FUNCTIONS ---
def is_valid_hex(color_str):
    return bool(re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', color_str))

# --- PDF GENERATOR ENGINE ---
class BackgroundCanvas(canvas.Canvas):
    def __init__(self, *args, bg_image=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.bg_image = bg_image

    def showPage(self):
        if self.bg_image and os.path.exists(self.bg_image):
            self.drawImage(self.bg_image, 0, 0, width=A4[0], height=A4[1])
        super().showPage()

def generate_pdf(excel_path, output_pdf, bg_image, custom_colors):
    df = pd.read_excel(excel_path)
    doc = SimpleDocTemplate(
        output_pdf, pagesize=A4,
        leftMargin=36, rightMargin=36, topMargin=54, bottomMargin=54
    )
    styles = getSampleStyleSheet()
    
    # تطبيق الألوان المخصصة من قاعدة البيانات
    pri_color = custom_colors.get("primary", "#1A237E")
    sec_color = custom_colors.get("secondary", "#212121")

    q_style = ParagraphStyle('QStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=colors.HexColor(pri_color))
    ans_style = ParagraphStyle('AnsStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=13, textColor=colors.HexColor(pri_color))
    
    opt_style = ParagraphStyle('OptStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=13, textColor=colors.HexColor(sec_color))
    exp_style = ParagraphStyle('ExpStyle', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=9, leading=12, textColor=colors.HexColor(sec_color))
    
    story = []
    for idx, row in df.iterrows():
        elements = []
        q_num = row.get('Q.No', idx + 1)
        q_text = str(row.get('Question', ''))
        elements.append(Paragraph(f"<b>Q{q_num}: {q_text}</b>", q_style))
        elements.append(Spacer(1, 4))
        
        for opt in ['A', 'B', 'C', 'D']:
            if pd.notna(row.get(opt)):
                elements.append(Paragraph(f"<b>({opt})</b> {row[opt]}", opt_style))
                elements.append(Spacer(1, 2))
        
        if pd.notna(row.get('Answer')):
            elements.append(Paragraph(f"<b>Correct Answer:</b> {row['Answer']}", ans_style))
            elements.append(Spacer(1, 2))
            
        if pd.notna(row.get('Explanation')):
            elements.append(Paragraph(f"<b>Explanation:</b> {row['Explanation']}", exp_style))
            
        elements.append(Spacer(1, 10))
        story.append(KeepTogether(elements))
        
    def make_canvas(*args, **kwargs):
        return BackgroundCanvas(*args, bg_image=bg_image, **kwargs)
        
    doc.build(story, canvasmaker=make_canvas)

# --- USER BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not db["subjects"]:
        await update.message.reply_text("👋 أهلاً بك!\n\nعذراً، لا توجد مواد متاحة حالياً. يرجى مراجعة المشرف.")
        return

    keyboard = []
    for key, val in db["subjects"].items():
        keyboard.append([InlineKeyboardButton(val["name"], callback_data=f"sub_{key}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 **أهلاً بك في بوت Med Crew PDF Booklet Generator**\n\n"
        "الرجاء اختيار المادة المراد إنشاء ملزمة لها:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def subject_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub_key = query.data.replace("sub_", "")
    
    db = load_db()
    if sub_key in db["subjects"]:
        context.user_data['selected_subject'] = sub_key
        sub_name = db["subjects"][sub_key]["name"]
        await query.edit_message_text(
            f"✅ تم اختيار مادة: **{sub_name}**\n\n"
            "قم الآن بإرسال ملف الـ Excel (`.xlsx`) المطلوب تحويله إلى ملزمة.",
            parse_mode="Markdown"
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sub_key = context.user_data.get('selected_subject')
    if not sub_key:
        await update.message.reply_text("⚠️ يرجى اختيار المادة أولاً بالضغط على /start")
        return

    doc = update.message.document
    if not doc.file_name.endswith('.xlsx'):
        await update.message.reply_text("❌ يرجى إرسال ملف Excel بصيغة `.xlsx` فقط.")
        return

    db = load_db()
    bg_image = db["subjects"][sub_key]["bg"]
    custom_colors = db.get("colors", {})

    status_msg = await update.message.reply_text("⏳ جاري معالجة الملف وتوليد ملزمة الـ PDF...")

    file = await context.bot.get_file(doc.file_id)
    excel_path = f"temp_{doc.file_id}.xlsx"
    pdf_path = f"MedCrew_{sub_key}_Booklet.pdf"

    await file.download_to_drive(excel_path)

    try:
        generate_pdf(excel_path, pdf_path, bg_image, custom_colors)
        await update.message.reply_document(
            document=open(pdf_path, 'rb'),
            caption=f"🎉 تم إنشاء ملزمة **{db['subjects'][sub_key]['name']}** بنجاح!"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء معالجة الملف:\n`{str(e)}`", parse_mode="Markdown")
    finally:
        if os.path.exists(excel_path): os.remove(excel_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)
        await status_msg.delete()

# --- ADMIN PANEL HANDLERS ---
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔐 **لوحة تحكم الأدمن**\n\nيرجى إدخال كلمة السر للاستمرار:", parse_mode="Markdown")
    return AUTH

async def admin_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADMIN_PASSWORD:
        keyboard = [
            [InlineKeyboardButton("➕ إضافة مادة جديدة", callback_data="add_sub")],
            [InlineKeyboardButton("🎨 تغيير ألوان الـ PDF", callback_data="edit_colors")],
            [InlineKeyboardButton("📋 عرض المواد الحالية", callback_data="list_sub")]
        ]
        await update.message.reply_text(
            "✅ **تم تسجيل الدخول بنجاح!**\n\nاختر ما تريد القيام به:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return WAIT_ACTION
    else:
        await update.message.reply_text("❌ كلمة السر خاطئة! تم إلغاء العملية.")
        return ConversationHandler.END

async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "add_sub":
        await query.edit_message_text("✏️ أرسل الآن **اسم المادة الجديدة** (مثال: `Anatomy 🫀`):", parse_mode="Markdown")
        return WAIT_SUB_NAME
        
    elif query.data == "edit_colors":
        await query.edit_message_text(
            "🎨 **إعدادات الألوان**\n\n"
            "أرسل أولاً كود **اللون الأساسي** (سيتم تطبيقه على السؤال والإجابة الصحيحة).\n"
            "يجب أن يكون بصيغة Hex (مثال: `#1A237E`):",
            parse_mode="Markdown"
        )
        return WAIT_PRI_COLOR
        
    elif query.data == "list_sub":
        db = load_db()
        msg = "📚 **المواد الحالية:**\n\n"
        if not db["subjects"]:
            msg += "لا يوجد أي مواد مضافة حالياً."
        else:
            for key, val in db["subjects"].items():
                msg += f"• **{val['name']}**\n"
        await query.edit_message_text(msg, parse_mode="Markdown")
        return ConversationHandler.END

# --- SUBJECT ADDITION FLOW ---
async def add_sub_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_sub_name'] = update.message.text
    await update.message.reply_text("🖼️ ممتاز! أرسل الآن **صورة الخلفية** الخاصة بها كصورة (Photo):")
    return WAIT_SUB_BG

async def add_sub_bg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1] if update.message.photo else None
    if not photo:
        await update.message.reply_text("❌ يرجى إرسال الصورة كـ Photo.")
        return WAIT_SUB_BG

    sub_name = context.user_data['new_sub_name']
    sub_key = sub_name.split()[0].lower()
    bg_filename = f"{sub_key}_bg.png"

    file = await context.bot.get_file(photo.file_id)
    await file.download_to_drive(bg_filename)

    db = load_db()
    db["subjects"][sub_key] = {"name": sub_name, "bg": bg_filename}
    save_db(db)

    await update.message.reply_text(f"🎉 تمت إضافة مادة **{sub_name}** بنجاح!")
    return ConversationHandler.END

# --- COLORS CUSTOMIZATION FLOW ---
async def add_pri_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    color = update.message.text.strip()
    if not is_valid_hex(color):
        await update.message.reply_text("❌ كود غير صحيح. يرجى إرسال الكود بصيغة صحيحة (مثال: `#1A237E`):")
        return WAIT_PRI_COLOR
        
    context.user_data['new_pri_color'] = color
    await update.message.reply_text(
        "✅ تم الحفظ.\n\nأرسل الآن كود **اللون الفرعي** (سيتم تطبيقه على الاختيارات والتفسير).\n"
        "(مثال: `#212121`):",
        parse_mode="Markdown"
    )
    return WAIT_SEC_COLOR

async def add_sec_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    color = update.message.text.strip()
    if not is_valid_hex(color):
        await update.message.reply_text("❌ كود غير صحيح. يرجى إرساله بصيغة صحيحة (مثال: `#212121`):")
        return WAIT_SEC_COLOR
        
    db = load_db()
    if "colors" not in db:
        db["colors"] = {}
        
    db["colors"]["primary"] = context.user_data['new_pri_color']
    db["colors"]["secondary"] = color
    save_db(db)

    await update.message.reply_text("🎉 **تم حفظ الألوان بنجاح!** سيتم تطبيقها فوراً على أي ملف PDF جديد.", parse_mode="Markdown")
    return ConversationHandler.END

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 تم الإلغاء والخروج من لوحة التحكم.")
    return ConversationHandler.END

# --- MAIN BOT INITIALIZATION ---
def main():
    keep_alive()  # Start Web Service for Render
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler('admin', admin_start)],
        states={
            AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_auth)],
            WAIT_ACTION: [CallbackQueryHandler(admin_action)],
            WAIT_SUB_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sub_name)],
            WAIT_SUB_BG: [MessageHandler(filters.PHOTO, add_sub_bg)],
            WAIT_PRI_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pri_color)],
            WAIT_SEC_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sec_color)]
        },
        fallbacks=[CommandHandler('cancel', admin_cancel)]
    )

    app.add_handler(admin_conv)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(subject_selected, pattern="^sub_"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("🤖 Bot is running with Dynamic Admin Customization...")
    app.run_polling()

if __name__ == '__main__':
    main()
```eof

### 📋 كيفية استخدام الميزات الجديدة (من التيليجرام):
1. ضعي التوكن الخاص بك في السطر 39، وارفعي الملف لـ GitHub.
2. ارفعي البوت على Render، ولما يشتغل ادخلي على البوت وأرسلي `/admin`.
3. اضغطي على زر **"تغيير ألوان الـ PDF"**:
   * البوت هيسألك عن **اللون الأساسي** (مثل `#1A237E`)، ابعتيه.
   * بعدها هيسألك عن **اللون الفرعي** (مثل `#212121`)، ابعتيه.
   * سيتم الحفظ فوراً، وأي ملزمة هتعمليها هتخرج بالألوان دي!

*(كما أضفت لك أمر `/cancel` في أي وقت تريدي الخروج من عملية الإضافة دون إكمالها).*
جاهزة للرفع فوراً! 🚀
