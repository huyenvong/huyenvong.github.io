(function () {
  "use strict";

  var SETTINGS_KEY = "hv:reader-settings";
  var READING_PREFIX = "hv:reading:";
  var READING_LIST_KEY = "hv:reading-list";

  var DEFAULT_SETTINGS = {
    fontSize: "medium",
    lineHeight: "comfortable",
    readerWidth: "medium"
  };

  var VALID_SETTINGS = {
    fontSize: ["small", "medium", "large", "extra-large"],
    lineHeight: ["compact", "comfortable", "spacious"],
    readerWidth: ["narrow", "medium", "wide"]
  };

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
      return true;
    } catch (error) {
      return false;
    }
  }

  function parseJson(value, fallback) {
    if (!value) {
      return fallback;
    }

    try {
      return JSON.parse(value);
    } catch (error) {
      return fallback;
    }
  }

  function debounce(callback, delay) {
    var timeoutId;

    return function () {
      var context = this;
      var argumentsList = arguments;

      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(function () {
        callback.apply(context, argumentsList);
      }, delay);
    };
  }

  function throttle(callback, delay) {
    var lastRun = 0;
    var timeoutId = null;

    return function () {
      var context = this;
      var argumentsList = arguments;
      var now = Date.now();
      var remaining = delay - (now - lastRun);

      if (remaining <= 0) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
        lastRun = now;
        callback.apply(context, argumentsList);
        return;
      }

      if (timeoutId !== null) {
        return;
      }

      timeoutId = window.setTimeout(function () {
        lastRun = Date.now();
        timeoutId = null;
        callback.apply(context, argumentsList);
      }, remaining);
    };
  }

  function getSettings() {
    var savedSettings = parseJson(
      readStorage(SETTINGS_KEY),
      {}
    );

    var settings = {
      fontSize: savedSettings.fontSize || DEFAULT_SETTINGS.fontSize,
      lineHeight:
        savedSettings.lineHeight || DEFAULT_SETTINGS.lineHeight,
      readerWidth:
        savedSettings.readerWidth || DEFAULT_SETTINGS.readerWidth
    };

    Object.keys(VALID_SETTINGS).forEach(function (settingName) {
      if (
        VALID_SETTINGS[settingName].indexOf(settings[settingName]) === -1
      ) {
        settings[settingName] = DEFAULT_SETTINGS[settingName];
      }
    });

    return settings;
  }

  function saveSettings(settings) {
    writeStorage(SETTINGS_KEY, JSON.stringify(settings));
  }

  function applySettings(settings) {
    var body = document.body;

    body.dataset.fontSize = settings.fontSize;
    body.dataset.lineHeight = settings.lineHeight;
    body.dataset.readerWidth = settings.readerWidth;

    document
      .querySelectorAll("[data-reader-setting]")
      .forEach(function (button) {
        var settingName = button.dataset.readerSetting;
        var settingValue = button.dataset.readerValue;
        var isActive = settings[settingName] === settingValue;

        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
  }

  function initialiseReaderSettings() {
    var settings = getSettings();

    applySettings(settings);

    document
      .querySelectorAll("[data-reader-setting]")
      .forEach(function (button) {
        button.addEventListener("click", function () {
          var settingName = button.dataset.readerSetting;
          var settingValue = button.dataset.readerValue;

          if (
            !VALID_SETTINGS[settingName] ||
            VALID_SETTINGS[settingName].indexOf(settingValue) === -1
          ) {
            return;
          }

          settings[settingName] = settingValue;
          saveSettings(settings);
          applySettings(settings);
        });
      });

    document
      .querySelectorAll("[data-reader-reset]")
      .forEach(function (button) {
        button.addEventListener("click", function () {
          settings = {
            fontSize: DEFAULT_SETTINGS.fontSize,
            lineHeight: DEFAULT_SETTINGS.lineHeight,
            readerWidth: DEFAULT_SETTINGS.readerWidth
          };

          saveSettings(settings);
          applySettings(settings);
        });
      });
  }

  function getReadingPercentage() {
    var documentElement = document.documentElement;
    var body = document.body;
    var scrollTop =
      window.scrollY ||
      documentElement.scrollTop ||
      body.scrollTop ||
      0;
    var scrollHeight = Math.max(
      body.scrollHeight,
      documentElement.scrollHeight,
      body.offsetHeight,
      documentElement.offsetHeight,
      body.clientHeight,
      documentElement.clientHeight
    );
    var availableHeight = scrollHeight - window.innerHeight;

    if (availableHeight <= 0) {
      return 100;
    }

    return Math.min(
      100,
      Math.max(0, Math.round((scrollTop / availableHeight) * 100))
    );
  }

  function updateProgressBar() {
    var progressBar = document.querySelector(
      "[data-reading-progress-bar]"
    );

    if (!progressBar) {
      return;
    }

    progressBar.style.width = getReadingPercentage() + "%";
  }

  function getReadingData() {
    var body = document.body;
    var bookSlug = body.dataset.bookSlug || "";
    var bookTitle = body.dataset.bookTitle || "";
    var chapterSlug = body.dataset.chapterSlug || "";
    var chapterTitle = body.dataset.chapterTitle || document.title;
    var chapterNumber = Number(body.dataset.chapterNumber || 0);

    if (!bookSlug || !chapterSlug) {
      return null;
    }

    return {
      bookSlug: bookSlug,
      bookTitle: bookTitle,
      chapterSlug: chapterSlug,
      chapterTitle: chapterTitle,
      chapterNumber: chapterNumber,
      url: window.location.pathname,
      percentage: getReadingPercentage(),
      updatedAt: new Date().toISOString()
    };
  }

  function saveReadingProgress() {
    var readingData = getReadingData();
    var readingList;

    if (!readingData) {
      return;
    }

    writeStorage(
      READING_PREFIX + readingData.bookSlug,
      JSON.stringify(readingData)
    );

    readingList = parseJson(readStorage(READING_LIST_KEY), {});

    if (
      !readingList ||
      typeof readingList !== "object" ||
      Array.isArray(readingList)
    ) {
      readingList = {};
    }

    readingList[readingData.bookSlug] = readingData;

    writeStorage(READING_LIST_KEY, JSON.stringify(readingList));
  }

  function restoreScrollPosition() {
    var body = document.body;
    var bookSlug = body.dataset.bookSlug || "";
    var chapterSlug = body.dataset.chapterSlug || "";
    var savedReading;
    var percentage;
    var availableHeight;

    if (!bookSlug || !chapterSlug) {
      return;
    }

    savedReading = parseJson(
      readStorage(READING_PREFIX + bookSlug),
      null
    );

    if (
      !savedReading ||
      savedReading.chapterSlug !== chapterSlug ||
      Number(savedReading.percentage) < 5 ||
      Number(savedReading.percentage) > 95
    ) {
      return;
    }

    percentage = Number(savedReading.percentage);

    window.requestAnimationFrame(function () {
      availableHeight =
        document.documentElement.scrollHeight - window.innerHeight;

      if (availableHeight > 0) {
        window.scrollTo({
          top: availableHeight * (percentage / 100),
          behavior: "auto"
        });
      }
    });
  }

  function initialiseReadingProgress() {
    var handleScroll = throttle(function () {
      updateProgressBar();
      saveReadingProgress();
    }, 250);

    updateProgressBar();
    saveReadingProgress();

    window.addEventListener("scroll", handleScroll, {
      passive: true
    });

    window.addEventListener(
      "resize",
      debounce(updateProgressBar, 150)
    );

    window.addEventListener("pagehide", saveReadingProgress);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") {
        saveReadingProgress();
      }
    });
  }

  function initialiseBackToTop() {
    var button = document.querySelector("[data-back-to-top]");

    if (!button) {
      return;
    }

    function updateButton() {
      var shouldShow = window.scrollY > 600;

      button.classList.toggle("is-visible", shouldShow);
      button.setAttribute(
        "aria-hidden",
        shouldShow ? "false" : "true"
      );
    }

    button.addEventListener("click", function () {
      window.scrollTo({
        top: 0,
        behavior: "smooth"
      });
    });

    window.addEventListener("scroll", throttle(updateButton, 120), {
      passive: true
    });

    updateButton();
  }

  function isTypingElement(element) {
    if (!element) {
      return false;
    }

    return (
      element.tagName === "INPUT" ||
      element.tagName === "TEXTAREA" ||
      element.tagName === "SELECT" ||
      element.isContentEditable
    );
  }

  function goToNavigationLink(selector) {
    var link = document.querySelector(selector);

    if (!link || !link.href || link.classList.contains("disabled")) {
      return;
    }

    saveReadingProgress();
    window.location.href = link.href;
  }

  function initialiseKeyboardNavigation() {
    document.addEventListener("keydown", function (event) {
      if (
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        isTypingElement(document.activeElement)
      ) {
        return;
      }

      if (event.key === "ArrowLeft") {
        goToNavigationLink("[data-previous-chapter]");
      }

      if (event.key === "ArrowRight") {
        goToNavigationLink("[data-next-chapter]");
      }
    });
  }

  function initialiseReader() {
    initialiseReaderSettings();
    initialiseReadingProgress();
    initialiseBackToTop();
    initialiseKeyboardNavigation();

    window.setTimeout(restoreScrollPosition, 80);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiseReader);
  } else {
    initialiseReader();
  }
})();
