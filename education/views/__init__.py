"""Сторінки сайту (тонкі view). Новий інтерфейс — views_ui.py; тут — точки входу за старими
URL-іменами, редиректи зі старих адрес (фаза 18), реєстрація і помічники для блоків уроку."""
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ..models import Grade, Item, Paragraph, Section
from ..services import answers_by_target, lesson_blocks


# --------------------------------------------------------------------------- уроки


def item_detail(request, item_id):
    """`/items/<id>/` — теорія уроку (views_ui.lesson_page)."""
    from .ui import lesson_page
    return lesson_page(request, get_object_or_404(Item.objects.select_related("paragraph__section__grade"), pk=item_id))


def play_lesson(request, kind, pk):
    """`/play/item|paragraph/<id>/` — екран гри (views_ui.play_page)."""
    from .ui import play_page
    return play_page(request, kind, get_object_or_404(Item if kind == "item" else Paragraph, pk=pk))


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


def get_lang(request):
    """Мова контенту уроків (фаза 20, беклог FE-0642): cookie `mw_lang`, виставляє js/lang.js
    на «Профілі». За замовчуванням — українська; `*_de` поля заповнені не для всього контенту,
    get_name()/_item_title() самі падають назад на українську там, де de ще порожнє."""
    return "de" if request.COOKIES.get("mw_lang") == "de" else "uk"


# --------------------------------------------------------------------------- старі адреси (фаза 18)
# Старий UI (список класів → розділів → § → пунктів) видалено. Адреси з закладок і пошуковиків
# ведуть постійним редиректом (301) на відповідне місце нової мапи.


def _map_url(grade, anchor=""):
    return reverse("grade_map_page", args=[grade.number]) + (f"#{anchor}" if anchor else "")


def old_grade_list(request):
    return HttpResponsePermanentRedirect(reverse("home"))


def old_section_list(request, grade_id):
    """`/grades/<pk>/sections/` (pk класу, не номер!) → мапа класу."""
    return HttpResponsePermanentRedirect(_map_url(get_object_or_404(Grade, pk=grade_id)))


def old_paragraph_list(request, section_id):
    """`/sections/<id>/paragraphs/` → мапа з першим уроком розділу."""
    section = get_object_or_404(Section.objects.select_related("grade"), pk=section_id)
    first = Paragraph.objects.filter(section=section).order_by("number").first()
    item = first.item_set.order_by("number").first() if first else None
    anchor = f"lesson-{item.pk}" if item else (f"lesson-p{first.pk}" if first else "")
    return HttpResponsePermanentRedirect(_map_url(section.grade, anchor))


def old_item_list(request, paragraph_id):
    """`/paragraphs/<id>/items/` → сторінка § `/paragraphs/<id>/`."""
    get_object_or_404(Paragraph, pk=paragraph_id)
    return HttpResponsePermanentRedirect(reverse("paragraph_page", args=[paragraph_id]))


# --------------------------------------------------------------------------- акаунт


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
