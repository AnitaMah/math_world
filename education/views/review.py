"""Сторінка /review/ для персоналу: швидка ручна перевірка вправ і підпунктів з needs_review."""
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .. import review
from ..models import ManualEdit, Textbook


def _filters(request):
    src = request.GET if request.method == "GET" else request.POST
    tb = src.get("tb") or ""
    textbook = Textbook.objects.filter(pk=tb).first() if tb.isdigit() else None
    return {"tb": tb if textbook else "", "p": src.get("p", "") if src.get("p", "").isdigit() else "",
            "kind": src.get("kind") if src.get("kind") in review.KINDS else "",
            "skipped": src.get("skipped") == "1"}, textbook


def _qs(f):
    return "&".join(f"{k}={'1' if v is True else v}" for k, v in f.items() if v)


def _get(kind, pk):
    if kind not in review.KINDS:
        raise Http404
    model = review.model_for(kind)
    qs = model.objects.all()
    qs = qs.select_related("textbook", "block__item__paragraph", "block__paragraph") if kind == "exercise" \
        else qs.select_related("exercise__textbook", "exercise__block__item__paragraph", "exercise__block__paragraph")
    return get_object_or_404(qs, pk=pk)


@staff_member_required
def review_index(request):
    f, textbook = _filters(request)
    items = review.queue(textbook, f["p"] or None, f["kind"] or None, f["skipped"])
    rows = [{"kind": k, "obj": o, "ex": review.exercise_of(o), "text": review.text_of(o),
             "url": reverse("review_detail", args=[k, o.pk]) + "?" + _qs(f)} for k, o in items[:300]]
    return render(request, "education/review/index.html", {
        "f": f, "textbooks": Textbook.objects.all(), "counters": review.counters(textbook),
        "rows": rows, "total": len(items), "shown": len(rows),
        "first_url": rows[0]["url"] if rows else "",
    })


@staff_member_required
def review_detail(request, kind, pk):
    obj = _get(kind, pk)
    f, textbook = _filters(request)
    ex = review.exercise_of(obj)
    back = reverse("review_index") + "?" + _qs(f)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            review.save_edit(obj, request.POST.get("text", ""), request.user)
        elif action == "confirm":
            review.save_edit(obj, review.text_of(obj), request.user)
        elif action == "skip":
            review.skip(obj, request.user)
        elif action == "unskip":
            review.unskip(obj, request.user)
        else:
            return HttpResponse(status=400)
        nxt = [(k, o) for k, o in review.queue(textbook, f["p"] or None, f["kind"] or None, f["skipped"])
               if not (k == kind and o.pk == obj.pk)]
        if action == "unskip" or not nxt:
            return redirect(back)
        return redirect(reverse("review_detail", args=[nxt[0][0], nxt[0][1].pk]) + "?" + _qs(f))
    return render(request, "education/review/detail.html", {
        "kind": kind, "obj": obj, "ex": ex, "text": review.text_of(obj), "f": f, "back": back,
        "paragraph": review.paragraph_of(obj), "has_crop": bool(ex.source_page),
        "subs": ex.subexercises.all(),
        "crop_url": reverse("review_crop", args=[kind, obj.pk]),
        "remaining": len(review.queue(textbook, f["p"] or None, f["kind"] or None, f["skipped"])),
        "history": ManualEdit.objects.filter(
            textbook=ex.textbook, exercise_number=ex.number, kind=kind, source_page=ex.source_page,
            sub_number=getattr(obj, "number", "") if kind == "subexercise" else "")[:5],
    })


@staff_member_required
def review_crop(request, kind, pk):
    from ..services import page_crop_png
    ex = review.exercise_of(_get(kind, pk))
    if not ex.source_page:
        raise Http404("У вправи немає сторінки")
    png = page_crop_png(ex.textbook, ex.source_page, ex.source_bbox)
    if png is None:
        raise Http404("Немає ні кешу сторінок, ні PDF")
    return HttpResponse(png, content_type="image/png")
