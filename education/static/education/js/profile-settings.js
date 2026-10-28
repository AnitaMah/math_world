// Налаштування на «Профілі»: тема (FE-0636), звук (FE-0637), мова уроків (FE-0642).
// Логіка — js/theme.js, js/sound.js, js/lang.js.
import { mountThemePicker } from "./theme.js";
import { mountSoundToggle } from "./sound.js";
import { mountLangPicker } from "./lang.js";

const themePicker = document.getElementById("themePicker");
if (themePicker) mountThemePicker(themePicker);

const soundToggle = document.getElementById("profileSoundToggle");
if (soundToggle) mountSoundToggle(soundToggle);

const langPicker = document.getElementById("langPicker");
if (langPicker) mountLangPicker(langPicker);
