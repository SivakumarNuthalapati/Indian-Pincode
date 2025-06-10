import os
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from fpdf import FPDF
import requests
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load pincode data
try:
    df = pd.read_csv('pincodes.csv')
    # Ensure column names match (adjust as needed based on your CSV)
    df.columns = df.columns.str.lower()
    required_columns = ['circlename', 'regionname', 'divisionname', 'officename', 
                       'pincode', 'officetype', 'delivery', 'district', 
                       'statename', 'latitude', 'longitude']
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing required column in CSV: {col}")
except Exception as e:
    logger.error(f"Error loading pincode data: {e}")
    raise

# Icons for different fields
ICONS = {
    'pincode': '📌',
    'office': '🏢',
    'type': '🏷️',
    'delivery': '📦',
    'circle': '🔵',
    'region': '🗺️',
    'division': '🏛️',
    'district': '📍',
    'state': '🏳️',
    'location': '🌐'
}

def search_pincode(query):
    """Search pincode database by pincode or location name"""
    try:
        # Try to convert query to integer (pincode search)
        try:
            pincode = int(query)
            results = df[df['pincode'] == pincode]
        except ValueError:
            # Location name search
            query = query.lower()
            results = df[df['officename'].str.lower().str.contains(query) | 
                         df['district'].str.lower().str.contains(query) |
                         df['statename'].str.lower().str.contains(query)]
        
        return results.to_dict('records')
    except Exception as e:
        logger.error(f"Error in search: {e}")
        return []

def format_result(result, index=None):
    """Format a single result with icons"""
    lines = []
    if index is not None:
        lines.append(f"🔹 <b>Result {index + 1}</b>")
    
    lines.extend([
        f"{ICONS['pincode']} <b>Pincode:</b> {result['pincode']}",
        f"{ICONS['office']} <b>Office:</b> {result['officename']}",
        f"{ICONS['type']} <b>Type:</b> {result['officetype']}",
        f"{ICONS['delivery']} <b>Delivery:</b> {result['delivery']}",
        f"{ICONS['circle']} <b>Circle:</b> {result['circlename']}",
        f"{ICONS['region']} <b>Region:</b> {result['regionname']}",
        f"{ICONS['division']} <b>Division:</b> {result['divisionname']}",
        f"{ICONS['district']} <b>District:</b> {result['district']}",
        f"{ICONS['state']} <b>State:</b> {result['statename']}",
    ])
    
    # Add Google Maps link if coordinates are available
    if pd.notna(result['latitude']) and pd.notna(result['longitude']):
        lat, lon = result['latitude'], result['longitude']
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"
        lines.append(f"{ICONS['location']} <a href='{maps_url}'>View on Google Maps</a>")
    
    return "\n".join(lines)

def create_pdf(results, query):
    """Create a PDF with search results"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Indian Pincode Search Results", ln=1, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(200, 10, txt=f"Search Query: {query}", ln=1, align='C')
    pdf.ln(10)
    
    # Add each result
    for i, result in enumerate(results):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt=f"Result {i + 1}", ln=1)
        pdf.set_font("Arial", '', 12)
        
        details = [
            f"Pincode: {result['pincode']}",
            f"Office: {result['officename']}",
            f"Type: {result['officetype']}",
            f"Delivery: {result['delivery']}",
            f"Circle: {result['circlename']}",
            f"Region: {result['regionname']}",
            f"Division: {result['divisionname']}",
            f"District: {result['district']}",
            f"State: {result['statename']}",
        ]
        
        for line in details:
            pdf.cell(200, 10, txt=line, ln=1)
        
        # Add Google Maps link if coordinates are available
        if pd.notna(result['latitude']) and pd.notna(result['longitude']):
            lat, lon = result['latitude'], result['longitude']
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            pdf.cell(200, 10, txt=f"Google Maps: {maps_url}", ln=1)
        
        pdf.ln(5)
    
    # Save PDF to temporary file
    pdf_path = f"pincode_results_{query}.pdf"
    pdf.output(pdf_path)
    return pdf_path

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    welcome_message = (
        "🔍 <b>Indian Pincode Search Bot</b>\n\n"
        "You can search by:\n"
        "• 6-digit pincode (e.g., 110001)\n"
        "• Office name (e.g., 'GPO')\n"
        "• District name (e.g., 'New Delhi')\n"
        "• State name (e.g., 'Maharashtra')\n\n"
        "Just type your query and I'll find matching pincodes!"
    )
    update.message.reply_text(welcome_message, parse_mode='HTML')

def handle_search(update: Update, context: CallbackContext) -> None:
    """Handle the pincode search query."""
    query = update.message.text.strip()
    if not query:
        update.message.reply_text("Please enter a pincode or location name to search.")
        return
    
    results = search_pincode(query)
    if not results:
        update.message.reply_text("❌ No results found. Please try a different query.")
        return
    
    # Store results in context for PDF generation
    context.user_data['last_results'] = results
    context.user_data['last_query'] = query
    
    # Send results (limited to 5 to avoid message flooding)
    for i, result in enumerate(results[:5]):
        reply_text = format_result(result, i)
        # Add PDF button to the last message
        reply_markup = None
        if i == len(results[:5]) - 1:
            if len(results) > 5:
                reply_text += f"\n\nℹ️ Showing 5 of {len(results)} results."
            reply_text += "\n\n📄 You can export all results to PDF:"
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("Export to PDF", callback_data=f"pdf_export:{query}")]
            ])
        
        update.message.reply_text(
            reply_text, 
            parse_mode='HTML', 
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    
    if len(results) > 5:
        update.message.reply_text(
            f"ℹ️ There are more results ({len(results)} total). Please refine your search for better results.",
            parse_mode='HTML'
        )

def export_pdf(update: Update, context: CallbackContext) -> None:
    """Handle PDF export callback"""
    query = update.callback_query
    query.answer()
    
    # Get the original query from callback data
    original_query = query.data.split(':', 1)[1]
    
    # Get results from user_data (stored during search)
    results = context.user_data.get('last_results', [])
    if not results:
        query.edit_message_text(text="Sorry, I couldn't find those results anymore. Please perform a new search.")
        return
    
    try:
        # Create PDF
        pdf_path = create_pdf(results, original_query)
        
        # Send PDF
        with open(pdf_path, 'rb') as pdf_file:
            query.message.reply_document(
                document=pdf_file,
                caption=f"Here are the pincode results for '{original_query}'",
                filename=f"pincode_results_{original_query}.pdf"
            )
        
        # Clean up
        os.remove(pdf_path)
        
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        query.message.reply_text("❌ Sorry, there was an error generating the PDF. Please try again.")

def error_handler(update: Update, context: CallbackContext) -> None:
    """Log errors and send a user-friendly message."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    if update and update.effective_message:
        update.effective_message.reply_text(
            "❌ Sorry, something went wrong. Please try again later or with a different query."
        )

def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    token = os.getenv('BOT_TOKEN')
    if not token:
        raise ValueError("No BOT_TOKEN found in environment variables")
    
    updater = Updater(token)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_search))
    dispatcher.add_handler(CallbackQueryHandler(export_pdf, pattern=r'^pdf_export:'))
    
    # Register error handler
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()