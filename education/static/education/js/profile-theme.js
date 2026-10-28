// Перемикач теми на «Профілі» (фаза 20, беклог FE-0636). Логіка — js/theme.js.
import { mountThemePicker } from "./theme.js";

const picker = document.getElementById("themePicker");
if (picker) mountThemePicker(picker);
