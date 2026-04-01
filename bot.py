import os
import logging
import tempfile
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

from converter import convert_to_webm

load_dotenv()  # reads .env file into os.environ

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_DOWNLOAD_SIZE_MB = 10


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send me a GIF and I'll convert it to a Telegram video sticker (.webm VP9).\n\n"
        "• GIFs longer than 3 seconds get trimmed\n\n"
        "Send the GIF <b>as a file</b> (use the attachment paperclip → File) "
        "to preserve original quality. Sending it inline lets Telegram re-encode it first.",
        parse_mode=ParseMode.HTML,
    )


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message

    #   message.animation → User sent GIF the normal way. Telegram has already
    #     re-encoded it as MPEG-4. We still get a downloadable video file.
    #   message.document (mime: image/gif) → User sent it explicitly "as a file."
    #     We get the raw GIF bytes. Usually better quality.
    if message.animation:
        file_obj = message.animation
        input_filename = "input.mp4"   # it's actually an MP4 at this point
        source_type = "animation (Telegram-converted MP4)"
    elif message.document and message.document.mime_type == "image/gif":
        file_obj = message.document
        input_filename = "input.gif"
        source_type = "GIF document"
    else:
        await message.reply_text("Please send a GIF file.")
        return

    # --- Size check before downloading ---
    size_bytes = file_obj.file_size or 0
    max_bytes = MAX_DOWNLOAD_SIZE_MB * 1024 * 1024

    if size_bytes > max_bytes:
        await message.reply_text(
            f"File too large: {size_bytes / 1024 / 1024:.1f} MB. "
            f"Maximum allowed: {MAX_DOWNLOAD_SIZE_MB} MB."
        )
        return

    logger.info("Received %s, %.1f KB", source_type, size_bytes / 1024)

    # Show the user we're working — this matters for slow conversions
    status = await message.reply_text("Downloading.")

    # tempfile.TemporaryDirectory auto-deletes everything when the `with` block exits,
    # even if an exception occurs. Crucial for not leaking temp files.
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = f"{tmpdir}/{input_filename}"
        output_path = f"{tmpdir}/sticker.webm"

        try:
            tg_file = await context.bot.get_file(file_obj.file_id)
            await tg_file.download_to_drive(input_path)
        except Exception as e:
            logger.exception("Download failed")
            await status.edit_text(f"Download failed: {e}")
            return

        await status.edit_text("Converting to VP9 WebM.")

        success, info = convert_to_webm(input_path, output_path)

        if not success:
            await status.edit_text(
                f"Conversion failed\n\n{info}",
                parse_mode=ParseMode.HTML,
            )
            return

        await status.edit_text("📤 Uploading…")

        try:
            with open(output_path, "rb") as f:
                await message.reply_document(
                    document=f,
                    filename="sticker.webm",
                    caption=(
                        f"Done. ({info})\n\n"
                    ),
                )
            await status.delete()

        except Exception as e:
            logger.exception("Upload failed")
            await status.edit_text(f"Upload failed: {e}")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN  not set. "
            "Add it to your .env file or environment variables."
        )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))

    # filters.ANIMATION catches Telegram-converted GIFs
    # filters.Document.GIF catches raw GIF files sent as documents
    app.add_handler(
        MessageHandler(filters.ANIMATION | filters.Document.GIF, handle_media)
    )

    logger.info("Stibot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
