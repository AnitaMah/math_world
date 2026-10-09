from pathlib import Path
import json

from django.conf import settings
from django.shortcuts import render, get_object_or_404

from .models import Grade, Section, Paragraph, Item, TheoryPractice
from .services import answers_by_target, lesson_blocks, playable_counts


# -------------------------
#   🔧 СЕРВІСНА ФУНКЦІЯ
# -------------------------

def load_map_data():
    """
    Завантажує JSON з мапою, якщо файл існує. Мапа -- візуальний бонус
    поверх звичайних списків нижче, тому відсутність файлу чи картинки
    не повинна ламати сторінку (шаблон рендерить її як необов'язковий
    оверлей).
    """
    json_path = Path(__file__).resolve().parent / "static" / "education" / "map_data_uk.json"
    if json_path.exists():
        with json_path.open(encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": [], "links": []}


def _lang(request):
    return "de" if request.GET.get("lang") == "de" else "uk"


def _base_context(request, **extra):
    lang = _lang(request)
    context = {
        "lang": lang,
        "current_lang_label": "Українська" if lang == "uk" else "Deutsch",
        "other_lang_label": "Deutsch" if lang == "uk" else "Українська",
        "toggle_query": f"lang={'de' if lang == 'uk' else 'uk'}",
        "map_data": load_map_data(),
        "show_links": True,
    }
    context.update(extra)
    return context


# -------------------------
#   📘 СПИСОК КЛАСІВ
# -------------------------

def grade_list(request):
    lang = _lang(request)
    grades = list(Grade.objects.select_related("subject").order_by("number"))

    context = _base_context(
        request,
        content={
            "grade_title": "Класи",
            "grade_lead": "Оберіть клас для перегляду тем",
        },
        grades=[
            {
                "id": g.id,
                "number": g.number,
                "name": g.get_name(lang),
                "subject": g.subject.name_de if lang == "de" and g.subject.name_de else g.subject.name_uk,
            }
            for g in grades
        ],
    )
    return render(request, "education/grade_list.html", context)


# -------------------------
#   📚 СПИСОК РОЗДІЛІВ
# -------------------------

def section_list(request, grade_id):
    lang = _lang(request)
    grade = get_object_or_404(Grade, pk=grade_id)
    sections = Section.objects.filter(grade=grade).order_by("number")

    context = _base_context(
        request,
        grade=grade.get_name(lang),
        grade_id=grade.id,
        sections=[
            {"id": s.id, "number": s.number, "name": s.get_name(lang)} for s in sections
        ],
        content={"sections": "Розділи", "back": "Назад"},
    )
    return render(request, "education/section_list.html", context)


# -------------------------
#   📄 СПИСОК ПАРАГРАФІВ
# -------------------------

def paragraph_list(request, section_id):
    lang = _lang(request)
    section = get_object_or_404(Section, pk=section_id)
    paragraphs = Paragraph.objects.filter(section=section).order_by("number")

    context = _base_context(
        request,
        section=section.get_name(lang),
        section_id=section.id,
        grade_id=section.grade_id,
        paragraphs=[
            {"id": p.id, "number": p.number, "name": p.get_name(lang)} for p in paragraphs
        ],
        content={"paragraphs": "Параграфи", "back": "Назад"},
    )
    return render(request, "education/paragraph_list.html", context)


# -------------------------
#   📝 СПИСОК ЗАВДАНЬ
# -------------------------

def _blocks_context(lesson):
    """Блоки уроку для шаблону _lesson_blocks.html: вправи з підпунктами, відповіді, рисунки."""
    blocks = []
    for block in lesson_blocks(lesson):
        exercises = []
        for ex in block.exercises.all():
            answers = answers_by_target(ex)
            exercises.append({
                "obj": ex,
                "subs": [_sub_context(s, answers.get(s.pk, {})) for s in ex.subexercises.all()],
                "answer": answers.get(None, {}),
                "has_answers": bool(answers),
                "figures": list(ex.figures.all()),
            })
        # Заголовок блоку — це рядок-маркер рубрики з OCR («Вправи», «Завдання ме 1 «Перевірте себе»…»):
        # він дублює назву типу і часто з помилками, тож показуємо лише назву типу.
        blocks.append({"obj": block, "exercises": exercises, "figures": list(block.figures.all())})
    return blocks


def _sub_context(sub, answer):
    shown = answer.get("book") or answer.get("computed") or ""
    other = answer.get("computed") if answer.get("book") and sub.answer_check == "mismatch" else ""
    return {"obj": sub, "answer": shown, "computed_other": other}


def _item_title(item, lang):
    """Назва пункту — перший рядок змісту («2. Цифри. Десятковий запис…»), а не перше речення:
    details_list ріже за крапкою, і «Цифри. Десятковий запис» ставало «Цифри.»."""
    text = item.content_de if lang == "de" and item.content_de else item.content
    return (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""


def item_list(request, paragraph_id):
    lang = _lang(request)
    paragraph = get_object_or_404(Paragraph.objects.select_related("section"), pk=paragraph_id)
    items = list(Item.objects.filter(paragraph=paragraph).order_by("number"))
    counts = playable_counts(items)
    from .game import get_player
    player = get_player(request, create=False)
    stars = dict(player.progress.filter(item__in=items).values_list("item_id", "stars")) if player else {}

    context = _base_context(
        request,
        paragraph=paragraph.get_name(lang),
        paragraph_id=paragraph.id,
        section_id=paragraph.section_id,
        grade_id=paragraph.section.grade_id,
        items=[
            {"id": i.id, "number": i.number, "title": _item_title(i, lang), "exercises": counts.get(i.id, 0),
             "stars": stars.get(i.id, 0)}
            for i in items
        ],
        # Урок = § (Тарасенкова) або блоки рівня § («Перевірте себе» у Мерзляка)
        blocks=_blocks_context(paragraph),
        content={"items": "Завдання", "back": "Назад"},
        media_url=settings.MEDIA_URL,
    )
    return render(request, "education/item_list.html", context)


# -------------------------
#   📘 ДЕТАЛІ ЗАВДАННЯ
# -------------------------

def item_detail(request, item_id):
    lang = _lang(request)
    item = get_object_or_404(Item.objects.select_related("paragraph__section"), pk=item_id)
    if getattr(settings, "NEW_UI", False):
        from .views_ui import lesson_page
        return lesson_page(request, item)
    paragraph = item.paragraph

    tp = TheoryPractice.objects.filter(item=item).first()

    context = _base_context(
        request,
        paragraph=paragraph.get_name(lang),
        paragraph_id=paragraph.id,
        section_id=paragraph.section_id,
        grade_id=paragraph.section.grade_id,
        item={
            "id": item.id,
            "number": item.number,
            "details": item.details_list(lang),
        },
        tp=tp,
        blocks=_blocks_context(item),
        media_url=settings.MEDIA_URL,
        content={"items": "Деталі завдання", "back": "Назад"},
    )
    return render(request, "education/item_detail.html", context)


# -------------------------
#   🎮 ГРА: УРОК ЯК ПОСЛІДОВНІСТЬ ЗАВДАНЬ
# -------------------------

def play_lesson(request, kind, pk):
    from django.urls import reverse
    lesson = get_object_or_404(Item if kind == "item" else Paragraph, pk=pk)
    if getattr(settings, "NEW_UI", False):
        from .views_ui import play_page
        return play_page(request, kind, lesson)
    if kind == "item":
        title, back = _item_title(lesson, "uk"), reverse("item_detail", args=[lesson.pk])
        api_url = reverse("api_play_item", args=[lesson.pk])
    else:
        title, back = lesson.name_uk, reverse("item_list", args=[lesson.pk])
        api_url = reverse("api_play_paragraph", args=[lesson.pk])
    return render(request, "education/play.html", {"title": title, "back_url": back, "api_url": api_url})


def signup(request):
    """Реєстрація: прогрес гостя з цієї сесії переноситься в новий акаунт (сигнал user_logged_in).

    `next` — з GET або прихованого поля форми; лише безпечні адреси цього сайту (інакше — на головну).
    """
    from django.contrib.auth import login
    from django.contrib.auth.forms import UserCreationForm
    from django.shortcuts import redirect
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        nxt = ""
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect(nxt or "home")
    return render(request, "registration/signup.html", {"form": form, "next": nxt})
