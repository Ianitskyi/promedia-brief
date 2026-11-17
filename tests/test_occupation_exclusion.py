"""Owner, 2026-11-17: appointments by the occupiers are not news for BRIEF."""
from brief.classify import excluded
from brief.util import config

EX = config("editorial.json")["exclude"]


def test_occupation_appointments_are_excluded():
    for t in ["Окупанти призначили російського військового керувати Новою Каховкою",
              "Гауляйтером Нової Каховки призначили офіцера РФ",
              "Призначили нового незаконного очільника окупованої Нової Каховки на Херсонщині",
              "Новий окупаційний очільник Нової Каховки фігурував у справі про «Новичок»"]:
        assert excluded({"title": t, "url": "https://x/1"}, EX), t


def test_other_news_about_occupation_stays():
    for t in ["Окупанти вдарили по Херсону: загинув чоловік", "ЗСУ звільнили село від окупантів",
              "Окупаційна влада депортує дітей з Херсонщини", "Кабмін призначив голову Херсонської ОВА"]:
        assert not excluded({"title": t, "url": "https://x/1"}, EX), t
