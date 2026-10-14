"""English / Persian UI strings with RTL support."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Language(str, Enum):
    ENGLISH = "en"
    PERSIAN = "fa"


@dataclass(frozen=True)
class Strings:
    language: Language
    rtl: bool
    app_title: str
    drop_hint: str
    target_format: str
    output_dir: str
    same_as_source: str
    browse: str
    advanced: str
    max_err: str
    reverse_direction: str
    verify: str
    overwrite: str
    ttc_index: str
    convert: str
    cancel: str
    lossless: str
    lossy: str
    lossy_warning: str
    open_folder: str
    copy_css: str
    font_info: str
    language_label: str
    sample_latin: str
    sample_persian: str
    sample_digits: str
    sample_zwnj: str
    sample_arabic: str
    preview_source: str
    preview_converted: str
    preview_woff2_note: str
    coverage: str
    status_ready: str
    status_working: str
    status_done: str
    status_cancelled: str
    clear_list: str
    add_files: str
    settings: str
    close: str
    error_title: str
    no_files: str
    copied: str
    verification_passed: str
    verification_failed: str
    issues: str
    profile: str
    theme: str
    history: str
    workers: str
    preserve_flavor: str
    axes: str
    compare: str


_EN = Strings(
    language=Language.ENGLISH,
    rtl=False,
    app_title="GlyphShift",
    drop_hint="Drop font files or folders here\n(or click to browse)",
    target_format="Target format",
    output_dir="Output directory",
    same_as_source="Same as source",
    browse="Browse…",
    advanced="Advanced",
    max_err="Max approximation error (em)",
    reverse_direction="Reverse contour direction (CFF→TTF)",
    verify="Verify after convert",
    overwrite="Overwrite existing outputs",
    ttc_index="TTC face index (empty = all)",
    convert="Convert",
    cancel="Cancel",
    lossless="LOSSLESS — container only; glyphs and features preserved",
    lossy="LOSSY — outline conversion; hints dropped / curves approximated",
    lossy_warning=(
        "This path changes outline technology. Glyphs, cmap and OpenType layout "
        "are preserved and verified, but hinting is dropped and CFF→TTF curves "
        "are approximated."
    ),
    open_folder="Open output folder",
    copy_css="Copy CSS @font-face",
    font_info="Font info",
    language_label="Language",
    sample_latin="The quick brown fox jumps over the lazy dog.",
    sample_persian="ژاله از بیشتر چرت‌های هوشمندانهٔ فارسی لذت می‌برد.",
    sample_digits="۰۱۲۳۴۵۶۷۸۹ ٠١٢٣٤٥٦٧٨٩",
    sample_zwnj="می‌روم، کتاب‌ها، دانش‌آموز",
    sample_arabic="بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
    preview_source="Source",
    preview_converted="Converted",
    preview_woff2_note="WOFF2 preview uses a temporary TTF/OTF unwrap.",
    coverage="Coverage",
    status_ready="Ready",
    status_working="Converting…",
    status_done="Done",
    status_cancelled="Cancelled",
    clear_list="Clear",
    add_files="Add files…",
    settings="Settings",
    close="Close",
    error_title="Error",
    no_files="Add at least one font file.",
    copied="Copied to clipboard",
    verification_passed="Verification passed",
    verification_failed="Verification failed",
    issues="Issues",
    profile="Profile",
    theme="Theme",
    history="History",
    workers="Parallel workers",
    preserve_flavor="Preserve WOFF metadata",
    axes="Variable axes",
    compare="Compare",
)

_FA = Strings(
    language=Language.PERSIAN,
    rtl=True,
    app_title="گلیف‌شیفت",
    drop_hint="فایل یا پوشه فونت را اینجا رها کنید\n(یا کلیک کنید)",
    target_format="فرمت خروجی",
    output_dir="پوشه خروجی",
    same_as_source="همان پوشه منبع",
    browse="انتخاب…",
    advanced="پیشرفته",
    max_err="حداکثر خطای تقریب (em)",
    reverse_direction="معکوس کردن جهت کانتور (CFF→TTF)",
    verify="اعتبارسنجی پس از تبدیل",
    overwrite="بازنویسی فایل‌های موجود",
    ttc_index="ایندکس چهره TTC (خالی = همه)",
    convert="تبدیل",
    cancel="لغو",
    lossless="بدون‌اتلاف — فقط ظرف؛ گلیف‌ها و ویژگی‌ها حفظ می‌شوند",
    lossy="با‌اتلاف — تبدیل اوت‌لاین؛ هینت حذف / منحنی تقریب",
    lossy_warning=(
        "این مسیر فناوری اوت‌لاین را تغییر می‌دهد. گلیف‌ها، cmap و لایه‌بندی "
        "OpenType حفظ و بررسی می‌شوند، اما هینتینگ حذف می‌شود و منحنی‌های "
        "CFF→TTF تقریب زده می‌شوند."
    ),
    open_folder="باز کردن پوشه خروجی",
    copy_css="کپی CSS @font-face",
    font_info="اطلاعات فونت",
    language_label="زبان",
    sample_latin="The quick brown fox jumps over the lazy dog.",
    sample_persian="ژاله از بیشتر چرت‌های هوشمندانهٔ فارسی لذت می‌برد.",
    sample_digits="۰۱۲۳۴۵۶۷۸۹ ٠١٢٣٤٥٦٧٨٩",
    sample_zwnj="می‌روم، کتاب‌ها، دانش‌آموز",
    sample_arabic="بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
    preview_source="منبع",
    preview_converted="خروجی",
    preview_woff2_note="پیش‌نمایش WOFF2 از یک TTF/OTF موقت استفاده می‌کند.",
    coverage="پوشش یونیکد",
    status_ready="آماده",
    status_working="در حال تبدیل…",
    status_done="انجام شد",
    status_cancelled="لغو شد",
    clear_list="پاک کردن",
    add_files="افزودن فایل…",
    settings="تنظیمات",
    close="بستن",
    error_title="خطا",
    no_files="حداقل یک فایل فونت اضافه کنید.",
    copied="در کلیپ‌بورد کپی شد",
    verification_passed="اعتبارسنجی موفق",
    verification_failed="اعتبارسنجی ناموفق",
    issues="مسائل",
    profile="پروفایل",
    theme="پوسته",
    history="تاریخچه",
    workers="کارگر موازی",
    preserve_flavor="حفظ متادیتای WOFF",
    axes="محورهای متغیر",
    compare="مقایسه",
)


def get_strings(lang: Language | str) -> Strings:
    if isinstance(lang, str):
        lang = Language(lang)
    return _FA if lang == Language.PERSIAN else _EN
