from autograde.segment import split


def test_basic_ids():
    assert split("Q1_A07", "Tumbuhan menyerap cahaya. Tumbuhan juga mengonsumsi CO2!") == [
        ("Q1_A07_s1", "Tumbuhan menyerap cahaya."), ("Q1_A07_s2", "Tumbuhan juga mengonsumsi CO2!")]


def test_abbreviations_kept():
    s = split("A", "Hasilnya glukosa, oksigen, dll. dan itu penting. Selesai?")
    assert [t for _, t in s] == ["Hasilnya glukosa, oksigen, dll. dan itu penting.", "Selesai?"]


def test_abbreviation_at_end():
    assert [t for _, t in split("A", "Bahan: air, CO2, dsb.")] == ["Bahan: air, CO2, dsb."]


def test_empty_answer():
    assert split("A", "") == [] and split("A", "   ") == []


def test_single_sentence_without_punctuation():
    assert split("A", "fotosintesis menghasilkan oksigen") == [("A_s1", "fotosintesis menghasilkan oksigen")]


def test_decimal_and_nfkc():
    assert [t for _, t in split("A", "Nilai 0.5 itu kecil. CO₂ diserap.")] == ["Nilai 0.5 itu kecil.", "CO2 diserap."]
