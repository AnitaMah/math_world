// Налаштування на «Профілі»: тема (FE-0636) і звук (FE-0637). Логіка — js/theme.js, js/sound.js.
import { mountThemePicker } from "./theme.js";
import { mountSoundToggle } from "./sound.js";

const themePicker = document.getElementById("themePicker");
if (themePicker) mountThemePicker(themePicker);

const soundToggle = document.getElementById("profileSoundToggle");
if (soundToggle) mountSoundToggle(soundToggle);
