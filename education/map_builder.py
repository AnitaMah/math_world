from .models import Grade, Section, Paragraph, Item
from django.urls import reverse


def build_map_data(lang="uk", focus_type=None, focus_id=None):
    """Build hierarchical map data.

    - If focus_type is None: return only top-level grade nodes.
    - If focus_type=='grade': return the grade node and its sections.
    - If focus_type=='section': return the section and its paragraphs.
    - If focus_type=='paragraph': return the paragraph and its items.
    - If focus_type=='item': return the item and its parent chain.

    Each node contains `id`, `name`, `level`, `color`, and `url` for navigation.
    """
    nodes = []
    links = []

    # Build full structure (grades -> sections -> paragraphs -> items)
    for grade in Grade.objects.all().order_by("number"):
        grade_id = f"g{grade.id}"
        nodes.append({
            "id": grade_id,
            "name": getattr(grade, f"name_{lang}", grade.name_uk),
            "level": 0,
            "color": "#29b6f6",
            "url": reverse('section_list', args=[grade.id]) + f"?lang={lang}",
        })

        for section in grade.section_set.all().order_by("number"):
            section_id = f"s{section.id}"
            nodes.append({
                "id": section_id,
                "name": getattr(section, f"name_{lang}", section.name_uk),
                "level": 1,
                "color": "#66bb6a",
                "url": reverse('paragraph_list', args=[section.id]) + f"?lang={lang}",
            })
            links.append({"from": grade_id, "to": section_id})

            for paragraph in section.paragraph_set.all().order_by("number"):
                paragraph_id = f"p{paragraph.id}"
                nodes.append({
                    "id": paragraph_id,
                    "name": getattr(paragraph, f"name_{lang}", paragraph.name_uk),
                    "level": 2,
                    "color": "#ffa726",
                    "url": reverse('item_list', args=[paragraph.id]) + f"?lang={lang}",
                })
                links.append({"from": section_id, "to": paragraph_id})

                for item in paragraph.item_set.all().order_by("number"):
                    item_id = f"i{item.id}"
                    # derive a short label for the item: prefer localized content field
                    content_field = 'content_de' if lang == 'de' else 'content'
                    raw = getattr(item, content_field, None) or getattr(item, 'content', '')
                    # use first line or truncate to keep labels short
                    label = (raw.splitlines()[0] if raw else '').strip()
                    if not label:
                        label = f"Item {item.number}"
                    short_label = (label[:60] + '...') if len(label) > 60 else label
                    nodes.append({
                        "id": item_id,
                        "name": f"{item.number}. {short_label}",
                        "level": 3,
                        "color": "#ab47bc",
                        "url": reverse('item_detail', args=[item.id]) + f"?lang={lang}",
                    })
                    links.append({"from": paragraph_id, "to": item_id})

    # Filter nodes/links according to focus
    if not focus_type:
        filtered_nodes = [n for n in nodes if n['level'] == 0]
        filtered_links = []
    elif focus_type == 'grade':
        gid = f"g{focus_id}"
        # include the grade and its immediate children
        child_ids = [l['to'] for l in links if l['from'] == gid]
        filtered_nodes = [n for n in nodes if n['id'] == gid or n['id'] in child_ids]
        filtered_links = [l for l in links if l['from'] == gid and l['to'] in child_ids]
    elif focus_type == 'section':
        sid = f"s{focus_id}"
        child_ids = [l['to'] for l in links if l['from'] == sid]
        parent = [l['from'] for l in links if l['to'] == sid]
        allowed = set(child_ids + parent + [sid])
        filtered_nodes = [n for n in nodes if n['id'] in allowed]
        filtered_links = [l for l in links if l['from'] in allowed and l['to'] in allowed]
    elif focus_type == 'paragraph':
        pid = f"p{focus_id}"
        child_ids = [l['to'] for l in links if l['from'] == pid]
        parent = [l['from'] for l in links if l['to'] == pid]
        allowed = set(child_ids + parent + [pid])
        filtered_nodes = [n for n in nodes if n['id'] in allowed]
        filtered_links = [l for l in links if l['from'] in allowed and l['to'] in allowed]
    elif focus_type == 'item':
        iid = f"i{focus_id}"
        parent = [l['from'] for l in links if l['to'] == iid]
        grandparent = [l['from'] for l in links if l['to'] in parent]
        allowed = set([iid] + parent + grandparent)
        filtered_nodes = [n for n in nodes if n['id'] in allowed]
        filtered_links = [l for l in links if l['from'] in allowed and l['to'] in allowed]
    else:
        filtered_nodes = nodes
        filtered_links = links

    return {"nodes": filtered_nodes, "links": filtered_links}
