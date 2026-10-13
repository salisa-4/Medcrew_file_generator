import os
import json
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters 
) 
import pandas as pd 
from reportlab.lib.pagesizes import A4 
from reportlab.lib import colors 
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether 
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle 
from reportlab.pdfgen import canvas 

# --- CONFIGURATION (From Environment Variables) --- 
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") # رابط موقعك على Koyeb 
PORT = int(os.environ.get("PORT", "8000")) 
DB_FILE = "database.json" 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO) 

# --- DATABASE LOAD --- 
def load_db():
    if not os.path.exists(DB_FILE): 
        return {"subjects": {}, "colors": {"primary": "#1A237E", "secondary": "#212121"}} 
    with open(DB_FILE, "r", encoding="utf-8") as f: 
        return json.load(f) 

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
        output_pdf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=54, bottomMargin=54
    ) 
    styles = getSampleStyleSheet() 
    
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
        elements.append(Paragraph(f"Q{q_num}: {q_text}", q_style)) 
        elements.append(Spacer(1, 4)) 
        
        for opt in ['A', 'B', 'C', 'D']:
            if pd.notna(row.get(opt)):
                elements.append(Paragraph(f"({opt}) {row[opt]}", opt_style))
                elements.append(Spacer(1, 2)) 
        if pd.notna(row.get('Answer')):
            elements.append(Paragraph(f"Correct Answer: {row['Answer']}", ans_style))
            elements.append(Spacer(1, 2)) 
        if pd.notna(row.get('Explanation')):
            elements.append(Paragraph(f"Explanation: {row['Explanation']}", exp_style)) 
        elements.append(Spacer(1, 10)) 
        story.append(KeepTogether(elements)) 
    
    def make_canvas(*args, **kwargs):
        return BackgroundCanvas(*args, bg_image=bg_image, **kwargs)
    
    doc.build(story, canvasmaker=make_canvas) 

# --- USER BOT HANDLERS --- 
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db() 
    if not db["subjects"]:
        await update.message.reply_text("👋 أهلاً بك!\n\nلا توجد مواد متاحة حالياً.") 
        return
        
    keyboard = [[InlineKeyboardButton(val["name"], callback_data=f"sub_{key}")] for key, val in db["subjects"].items()] 
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
            f"✅ تم اختيار مادة: **{sub_name}**\n\nقم الآن بإرسال ملف الـ Excel (`.xlsx`).", 
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
        await update.message.reply_text(f"❌ حدث خطأ:\n`{str(e)}`", parse_mode="Markdown") 
    finally:
        if os.path.exists(excel_path): os.remove(excel_path) 
        if os.path.exists(pdf_path): os.remove(pdf_path)
        await status_msg.delete()
        
# --- MAIN INITIALIZATION --- 
def main():
    if not BOT_TOKEN: 
        print("❌ ERROR: BOT_TOKEN is missing!") 
        return 
    
    app = ApplicationBuilder().token(BOT_TOKEN).build() 
    
    app.add_handler(CommandHandler('start', start)) 
    app.add_handler(CallbackQueryHandler(subject_selected, pattern="^sub_")) 
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document)) 
    
    if WEBHOOK_URL: 
        # Run Webhook Mode (For Koyeb/Production) 
        print(f"🚀 Starting Webhook on port {PORT}...") 
        app.run_webhook( 
            listen="0.0.0.0", 
            port=PORT, 
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        ) 
    else: 
        # Run Polling Mode (For Local Testing) 
        print("🤖 Starting Polling Mode...") 
        app.run_polling() 
        
if __name__ == '__main__': 
    main() 
