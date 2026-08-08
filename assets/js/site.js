(function () {
  "use strict";

  var STORAGE_KEYS = {
    theme: "hv:theme"
  };

  var VALID_THEMES = ["auto", "light", "dark"];
  var systemDarkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      return;
    }
  }

  function getSavedTheme() {
    var savedTheme = readStorage(STORAGE_KEYS.theme);

    if (VALID_THEMES.indexOf(savedTheme) !== -1) {
      return savedTheme;
    }

    return "auto";
  }

  function getEffectiveTheme(theme) {
    if (theme === "auto") {
      return systemDarkQuery.matches ? "dark" : "light";
    }

    return theme;
  }

  function applyTheme(theme) {
    var selectedTheme =
      VALID_THEMES.indexOf(theme) !== -1 ? theme : "auto";
    var effectiveTheme = getEffectiveTheme(selectedTheme);
    var root = document.documentElement;

    root.dataset.themePreference = selectedTheme;
    root.dataset.theme = effectiveTheme;
    root.style.colorScheme = effectiveTheme;

    updateThemeControls(selectedTheme, effectiveTheme);

    document.dispatchEvent(
      new CustomEvent("hv:themechange", {
        detail: {
          preference: selectedTheme,
          effective: effectiveTheme
        }
      })
    );
  }

  function saveAndApplyTheme(theme) {
    writeStorage(STORAGE_KEYS.theme, theme);
    applyTheme(theme);
  }

  function updateThemeControls(selectedTheme, effectiveTheme) {
    var themeButtons = document.querySelectorAll("[data-theme-option]");
    var themeToggles = document.querySelectorAll("[data-theme-toggle]");

    themeButtons.forEach(function (button) {
      var isActive = button.dataset.themeOption === selectedTheme;

      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });

    themeToggles.forEach(function (button) {
      var label =
        effectiveTheme === "dark"
          ? "Chuyển sang chế độ sáng"
          : "Chuyển sang chế độ tối";

      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.dataset.activeTheme = effectiveTheme;
    });
  }

  function initialiseThemeControls() {
    document.querySelectorAll("[data-theme-option]").forEach(function (button) {
      button.addEventListener("click", function () {
        saveAndApplyTheme(button.dataset.themeOption);
      });
    });

    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        var currentTheme = document.documentElement.dataset.theme;
        var nextTheme = currentTheme === "dark" ? "light" : "dark";

        saveAndApplyTheme(nextTheme);
      });
    });
  }

  function closeMobileMenu() {
    var menu = document.querySelector("[data-mobile-menu]");
    var toggle = document.querySelector("[data-menu-toggle]");

    if (!menu || !toggle) {
      return;
    }

    menu.classList.remove("is-open");
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("menu-open");
  }

  function openMobileMenu() {
    var menu = document.querySelector("[data-mobile-menu]");
    var toggle = document.querySelector("[data-menu-toggle]");

    if (!menu || !toggle) {
      return;
    }

    menu.hidden = false;
    menu.classList.add("is-open");
    toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("menu-open");
  }

  function initialiseMobileMenu() {
    var menu = document.querySelector("[data-mobile-menu]");
    var toggle = document.querySelector("[data-menu-toggle]");

    if (!menu || !toggle) {
      return;
    }

    toggle.addEventListener("click", function () {
      var isOpen = toggle.getAttribute("aria-expanded") === "true";

      if (isOpen) {
        closeMobileMenu();
      } else {
        openMobileMenu();
      }
    });

    menu.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", closeMobileMenu);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeMobileMenu();
      }
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 720) {
        closeMobileMenu();
      }
    });
  }

  function closeDisclosure(disclosure) {
    var trigger = disclosure.querySelector("[aria-expanded]");
    var panel = disclosure.querySelector("[data-disclosure-panel]");

    if (!trigger || !panel) {
      return;
    }

    trigger.setAttribute("aria-expanded", "false");
    panel.hidden = true;
  }

  function initialiseDisclosures() {
    var disclosures = document.querySelectorAll("[data-disclosure]");

    disclosures.forEach(function (disclosure) {
      var trigger = disclosure.querySelector("[aria-expanded]");
      var panel = disclosure.querySelector("[data-disclosure-panel]");

      if (!trigger || !panel) {
        return;
      }

      trigger.addEventListener("click", function () {
        var isOpen = trigger.getAttribute("aria-expanded") === "true";

        disclosures.forEach(function (otherDisclosure) {
          if (otherDisclosure !== disclosure) {
            closeDisclosure(otherDisclosure);
          }
        });

        trigger.setAttribute("aria-expanded", String(!isOpen));
        panel.hidden = isOpen;
      });
    });

    document.addEventListener("click", function (event) {
      disclosures.forEach(function (disclosure) {
        if (!disclosure.contains(event.target)) {
          closeDisclosure(disclosure);
        }
      });
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") {
        return;
      }

      disclosures.forEach(closeDisclosure);
    });
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }

    return new Promise(function (resolve, reject) {
      var textarea = document.createElement("textarea");

      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();

      try {
        var copied = document.execCommand("copy");
        document.body.removeChild(textarea);

        if (copied) {
          resolve();
        } else {
          reject(new Error("Không thể sao chép."));
        }
      } catch (error) {
        document.body.removeChild(textarea);
        reject(error);
      }
    });
  }

  function temporarilyChangeButtonText(button, text) {
    var textElement = button.querySelector("[data-button-text]");
    var originalText;

    if (!textElement) {
      return;
    }

    originalText = textElement.textContent;
    textElement.textContent = text;

    window.setTimeout(function () {
      textElement.textContent = originalText;
    }, 1800);
  }

  function initialiseShareButtons() {
    document.querySelectorAll("[data-share-button]").forEach(function (button) {
      button.addEventListener("click", function () {
        var shareTitle =
          button.dataset.shareTitle || document.title || "Huyền Võng";
        var shareText = button.dataset.shareText || "";
        var shareUrl =
          button.dataset.shareUrl ||
          window.location.href.split("#")[0];

        if (navigator.share) {
          navigator
            .share({
              title: shareTitle,
              text: shareText,
              url: shareUrl
            })
            .catch(function (error) {
              if (error && error.name !== "AbortError") {
                return;
              }
            });

          return;
        }

        copyText(shareUrl)
          .then(function () {
            temporarilyChangeButtonText(button, "Đã sao chép");
          })
          .catch(function () {
            temporarilyChangeButtonText(button, "Không thể sao chép");
          });
      });
    });
  }

  function secureExternalLinks() {
    document.querySelectorAll('a[target="_blank"]').forEach(function (link) {
      var relValues = (link.getAttribute("rel") || "")
        .split(/\s+/)
        .filter(Boolean);

      ["noopener", "noreferrer"].forEach(function (value) {
        if (relValues.indexOf(value) === -1) {
          relValues.push(value);
        }
      });

      link.setAttribute("rel", relValues.join(" "));
    });
  }

  function updateCurrentYear() {
    document.querySelectorAll("[data-current-year]").forEach(function (element) {
      element.textContent = String(new Date().getFullYear());
    });
  }

  function handleSystemThemeChange() {
    if (getSavedTheme() === "auto") {
      applyTheme("auto");
    }
  }

  function initialiseSite() {
    initialiseThemeControls();
    initialiseMobileMenu();
    initialiseDisclosures();
    initialiseShareButtons();
    secureExternalLinks();
    updateCurrentYear();
    updateThemeControls(
      getSavedTheme(),
      getEffectiveTheme(getSavedTheme())
    );
  }

  applyTheme(getSavedTheme());

  if (typeof systemDarkQuery.addEventListener === "function") {
    systemDarkQuery.addEventListener("change", handleSystemThemeChange);
  } else if (typeof systemDarkQuery.addListener === "function") {
    systemDarkQuery.addListener(handleSystemThemeChange);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiseSite);
  } else {
    initialiseSite();
  }
})();
