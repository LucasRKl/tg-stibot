
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Telegram hard limits
MAX_OUTPUT_SIZE_KB = 256
TARGET_SIZE = 512        # pixel dimensions must be 512x512
MAX_DURATION_SEC = 3
MAX_FPS = 30


def convert_to_webm(input_path: str, output_path: str) -> tuple[bool, str]:
    """
    Convert GIF files to video sticker.

    Returns: (success: bool, info_message: str)
    """

    #Set Scaling and fps
    vf = (
        f"scale={TARGET_SIZE}:{TARGET_SIZE}:force_original_aspect_ratio=decrease,"
        f"fps={MAX_FPS}"
    )

    # Progressively downsize till the file fits under 256KB.
    #
    # -pix_fmt yuva420p: Y=luma, U/V=chroma, A=alpha. Allows transparency.
    #
    # -an: strip audio
    for crf in [33, 40, 48, 56, 63]:
        cmd = [
            "ffmpeg",
            "-y",                        # overwrite output without asking
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libvpx-vp9",
            "-b:v", "0",                 # REQUIRED for CRF mode in VP9
            "-crf", str(crf),
            "-pix_fmt", "yuva420p",      # VP9 + alpha channel
            "-an",                       # no audio
            "-t", str(MAX_DURATION_SEC), # hard cut at 3 seconds
            "-f", "webm",
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,     
                text=True,
                timeout=90,              
            )
        except subprocess.TimeoutExpired:
            return False, "ffmpeg timeout, GIF might be too complex."

        if result.returncode != 0:
            # Crops error message
            error_tail = result.stderr.strip().splitlines()
            last_lines = "\n".join(error_tail[-5:])
            logger.error("FFmpeg failed:\n%s", result.stderr)
            return False, f"FFmpeg conversion failed:\n<code>{last_lines}</code>"

        # Check size
        size_kb = Path(output_path).stat().st_size / 1024
        logger.info("CRF %d → %.1f KB", crf, size_kb)

        if size_kb <= MAX_OUTPUT_SIZE_KB:
            return True, f"CRF {crf} → {size_kb:.1f} KB"

    # If it can't fit under 256KB afte processing:
    final_size_kb = Path(output_path).stat().st_size / 1024
    return False, (
        f"Cannot compress below {MAX_OUTPUT_SIZE_KB} KB "
        f"(best attempt: {final_size_kb:.0f} KB). "
        "Try a smaller GIF."
    )