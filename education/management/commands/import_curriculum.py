import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Grade, Item, Paragraph, Section, TheoryPractice
from utils.llm_client import DEFAULT_MODEL, send_llm_prompt


CURRICULUM_PROMPT = """
You are a curriculum architect. Convert the raw text below into JSON for a math program.
Return ONLY valid JSON with this shape:
{
  "grades": [
    {
      "number": <int>,
      "name_uk": <str>,
      "name_de": <str or null>,
      "theme_uk": <str>,
      "theme_de": <str or null>,
      "sections": [
        {
          "number": <int>,
          "name_uk": <str>,
          "name_de": <str or null>,
          "paragraphs": [
            {
              "number": <int>,
              "name_uk": <str>,
              "name_de": <str or null>,
              "items": [
                {"number": <int>, "content": <str>, "content_de": <str or null>}
              ]
            }
          ]
        }
      ]
    }
  ]
}
Text to convert:
"""


def _generate_theory_practice(prompt_text: str, model: str) -> tuple[str, str]:
    enrichment_prompt = (
        "Згенеруй стислий блок 'Теорія' та блок 'Практика' у форматі JSON "
        "{\"theory\": \"...\", \"practice\": \"...\"} для теми: "
        f"{prompt_text}"
    )
    response = send_llm_prompt(enrichment_prompt, model=model)
    try:
        parsed = json.loads(response)
        return parsed.get("theory", ""), parsed.get("practice", "")
    except Exception:
        return response, ""


class Command(BaseCommand):
    help = "Import a curriculum text file via local Ollama and fill the database (grades → sections → paragraphs → items)."

    def add_arguments(self, parser):
        parser.add_argument("text_path", type=str, help="Path to a UTF-8 text document with the curriculum")
        parser.add_argument(
            "--model",
            default=DEFAULT_MODEL,
            help="Ollama model name to use for parsing (default from utils.llm_client)",
        )
        parser.add_argument(
            "--generate-details",
            action="store_true",
            help="Also generate theory/practice blocks for each item using the LLM",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse with the LLM but do not write to the database",
        )

    def handle(self, *args, **options):
        text_path = Path(options["text_path"])
        if not text_path.exists():
            raise CommandError(f"File not found: {text_path}")

        raw_text = text_path.read_text(encoding="utf-8")
        prompt = CURRICULUM_PROMPT + raw_text
        self.stdout.write(self.style.WARNING(f"Sending curriculum to Ollama model '{options['model']}'..."))
        response = send_llm_prompt(prompt, model=options["model"])

        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            raise CommandError(f"LLM did not return JSON: {exc}\nRaw response:\n{response}") from exc

        grades_data = payload.get("grades", [])
        if not grades_data:
            raise CommandError("No grades found in parsed payload")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Parsed {len(grades_data)} grades (dry run, no writes)"))
            return

        with transaction.atomic():
            for grade_data in grades_data:
                grade = Grade.objects.create(
                    number=grade_data.get("number") or 0,
                    name_uk=grade_data.get("name_uk") or "",
                    name_de=grade_data.get("name_de") or None,
                    theme_uk=grade_data.get("theme_uk") or "",
                    theme_de=grade_data.get("theme_de") or None,
                )
                for section_data in grade_data.get("sections", []):
                    section = Section.objects.create(
                        grade=grade,
                        number=section_data.get("number") or 0,
                        name_uk=section_data.get("name_uk") or "",
                        name_de=section_data.get("name_de") or None,
                    )
                    for paragraph_data in section_data.get("paragraphs", []):
                        paragraph = Paragraph.objects.create(
                            section=section,
                            number=paragraph_data.get("number") or 0,
                            name_uk=paragraph_data.get("name_uk") or "",
                            name_de=paragraph_data.get("name_de") or None,
                        )
                        for item_data in paragraph_data.get("items", []):
                            item = Item.objects.create(
                                paragraph=paragraph,
                                number=item_data.get("number") or 0,
                                content=item_data.get("content") or "",
                                content_de=item_data.get("content_de") or None,
                            )
                            if options["generate_details"]:
                                theory, practice = _generate_theory_practice(item.content, options["model"])
                                TheoryPractice.objects.update_or_create(
                                    item=item,
                                    defaults={"theory": theory, "practice": practice},
                                )

        self.stdout.write(self.style.SUCCESS(f"Imported {len(grades_data)} grades via Ollama"))
