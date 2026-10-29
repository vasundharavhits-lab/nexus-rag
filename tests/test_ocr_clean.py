# the OCR clean-up must not throw away text just because it is not English
from app import ocr

HI = "इस आत्मा को शस्त्रादि नहीं काट सकते, इसको आग जला नहीं सकती।"


def test_hindi_lines_are_kept():
    out = ocr.clean_ocr_text(HI + "\nवायु नहीं सुखा सकता", "eng+hin+san")
    assert HI.rstrip("।") in out and "वायु नहीं सुखा सकता" in out


def test_one_letter_hindi_word_at_the_start_is_not_trimmed():
    line = "न चैनं क्लेदयन्त्यापो न शोषयति मारुतः"
    assert ocr.clean_ocr_text(line, "hin").startswith("न ")


def test_noise_lines_are_dropped_in_any_script():
    junk = "| ~ ^ ` \u00b6 \u25a0 \u25a1\n\u00a3 \u00a5 \u00a7 \u00b6 \u00a9 \u00ae"
    assert ocr.clean_ocr_text(junk, "eng+hin") == ""
    assert HI.split("\u0964")[0] in ocr.clean_ocr_text(junk + "\n" + HI, "eng+hin")


def test_arabic_chinese_cyrillic_survive():
    for line in ("افتتحت العيادة في عام الف وتسعمائة وسبعة وثمانين", "东风诊所于一九八七年开业并由王芳管理",
                 "Клиника была открыта в тысяча девятьсот восемьдесят седьмом году"):
        assert line in ocr.clean_ocr_text(line, "eng+ara+chi_sim+rus")


def test_english_only_scans_still_drop_mis_read_other_scripts():
    mis_read = "aA el uals ca eal iN oy ke"            # Sanskrit read as Latin letters
    good = "The clinic is managed by the city council and funded each year."
    out = ocr.clean_ocr_text(mis_read + "\n" + good, "eng")
    assert good.rstrip(".") in out and "uals" not in out


def test_latin_edge_debris_is_still_trimmed():
    assert ocr.clean_ocr_text("the sacrificer pours the oblation into the fire f", "eng") == \
        "the sacrificer pours the oblation into the fire"


def test_auto_language_choice():
    assert ocr.pick_langs([], {"eng", "hin", "san", "osd"}) == "eng+hin+san"           # few packs: all of them, English first
    assert ocr.langs_for_scripts(["Devanagari"], {"eng", "hin", "san", "tam", "fra", "osd"}) == "eng+hin+san"
    assert ocr.langs_for_scripts(["Tamil", "Latin"], {"eng", "hin", "tam", "fra", "osd"}) == "eng+tam+fra"
