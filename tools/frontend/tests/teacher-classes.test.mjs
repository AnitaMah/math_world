// Тести js/teacher-classes.js (node:test): який клас показувати в режимі вчителя (фаза 20, FE-0645).
import { test } from "node:test";
import assert from "node:assert/strict";
import { pickDefaultClassId } from "../../../education/static/education/js/teacher-classes.js";

const classes = [{ id: 1, name: "5-А" }, { id: 2, name: "5-Б" }];

test("pickDefaultClassId: запам'ятований клас лишається, якщо він ще в списку", () => {
  assert.equal(pickDefaultClassId(classes, 2), 2);
});

test("pickDefaultClassId: нема запам'ятованого — перший клас зі списку", () => {
  assert.equal(pickDefaultClassId(classes, null), 1);
});

test("pickDefaultClassId: запам'ятований клас зник (учителя прибрали з нього) — перший зі списку", () => {
  assert.equal(pickDefaultClassId(classes, 999), 1);
});

test("pickDefaultClassId: класів нема — null", () => {
  assert.equal(pickDefaultClassId([], 1), null);
  assert.equal(pickDefaultClassId([], null), null);
});
