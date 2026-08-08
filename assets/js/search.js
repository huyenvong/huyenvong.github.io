(function () {
  "use strict";

  function normaliseText(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function getSearchQueryFromUrl() {
    var parameters = new URLSearchParams(window.location.search);

    return parameters.get("q") || "";
  }

  function updateSearchUrl(query) {
    if (!window.history || !window.history.replaceState) {
      return;
    }

    var url = new URL(window.location.href);
    var cleanQuery = query.trim();

    if (cleanQuery) {
      url.searchParams.set("q", cleanQuery);
    } else {
      url.searchParams.delete("q");
    }

    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
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

  function initialiseSearch(searchRoot) {
    var input = searchRoot.querySelector("[data-search-input]");
    var status = searchRoot.querySelector("[data-search-status]");
    var emptyState = searchRoot.querySelector("[data-search-empty]");
    var cards = Array.from(
      searchRoot.querySelectorAll("[data-book-card]")
    );

    if (!input || cards.length === 0) {
      return;
    }

    cards.forEach(function (card) {
      card.dataset.normalisedSearchText = normaliseText(
        card.dataset.searchText || card.textContent
      );
    });

    function runSearch(options) {
      var settings = options || {};
      var rawQuery = input.value;
      var query = normaliseText(rawQuery);
      var words = query.split(" ").filter(Boolean);
      var visibleCount = 0;

      cards.forEach(function (card) {
        var searchableText = card.dataset.normalisedSearchText;
        var isMatch =
          words.length === 0 ||
          words.every(function (word) {
            return searchableText.indexOf(word) !== -1;
          });

        card.hidden = !isMatch;

        if (isMatch) {
          visibleCount += 1;
        }
      });

      if (emptyState) {
        emptyState.hidden = visibleCount !== 0;
      }

      if (status) {
        if (!query) {
          status.textContent =
            cards.length + " truyện đang được hiển thị.";
        } else if (visibleCount === 0) {
          status.textContent =
            'Không tìm thấy truyện phù hợp với “' +
            rawQuery.trim() +
            '”.';
        } else {
          status.textContent =
            "Tìm thấy " + visibleCount + " truyện phù hợp.";
        }
      }

      if (settings.updateUrl !== false) {
        updateSearchUrl(rawQuery);
      }
    }

    var debouncedSearch = debounce(function () {
      runSearch({
        updateUrl: true
      });
    }, 180);

    input.addEventListener("input", debouncedSearch);

    input.addEventListener("search", function () {
      runSearch({
        updateUrl: true
      });
    });

    document.addEventListener("keydown", function (event) {
      var activeElement = document.activeElement;
      var isTyping =
        activeElement &&
        (activeElement.tagName === "INPUT" ||
          activeElement.tagName === "TEXTAREA" ||
          activeElement.isContentEditable);

      if (event.key === "/" && !isTyping) {
        event.preventDefault();
        input.focus();
      }

      if (event.key === "Escape" && activeElement === input) {
        input.value = "";
        runSearch({
          updateUrl: true
        });
        input.blur();
      }
    });

    input.value = getSearchQueryFromUrl();

    runSearch({
      updateUrl: false
    });
  }

  function initialiseAllSearchAreas() {
    document.querySelectorAll("[data-search-root]").forEach(initialiseSearch);
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      initialiseAllSearchAreas
    );
  } else {
    initialiseAllSearchAreas();
  }
})();
