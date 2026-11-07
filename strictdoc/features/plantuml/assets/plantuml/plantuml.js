/*
 * Renders PlantUML diagrams in place as inline SVG, using the locally
 * vendored PlantUML engine (plantuml-core.js plus its Graphviz/Viz.js
 * dependency, viz-global.js). No server round trip is involved: diagram
 * source never leaves the browser.
 *
 * Two kinds of blocks are rendered:
 *
 * - <pre class="plantuml">: the text of the block is PlantUML source.
 *
 * - <div class="sysml_diagram" data-sysml-set="..." data-sysml-options="...">:
 *   a diagram of SysML v2 files (see strictdoc/backend/sysml/
 *   plantuml_diagram.py). The files are the <script type="text/sysml">
 *   children of the <div class="sysml_sources"> with the same
 *   data-sysml-set. sysmlToPlantUml() of the engine turns them into PlantUML
 *   with the options, which is then rendered. A block with data-sysml-lazy
 *   is rendered when it comes near the viewport. Errors are shown in the
 *   block.
 *
 * Loaded as a classic script, not a module: ES module scripts are
 * CORS-blocked when a document is opened via file:// (e.g. StrictDoc's own
 * HTML2PDF export, or a user opening exported HTML directly from disk),
 * while classic scripts are not. plantuml-core.js is likewise vendored as a
 * classic script exposing window.PlantUMLCore instead of using ESM export.
 */
(function () {
  "use strict";

  // The engine loads the scripts it needs on demand (elk.bundled.js,
  // standard library bundles) relative to this base.
  if (document.currentScript && !window.PLANTUML_STDLIB_BASE) {
    window.PLANTUML_STDLIB_BASE = document.currentScript.src.replace(
      /[^/]*$/,
      ""
    );
  }

  function renderSource(lines) {
    return new Promise(function (resolve, reject) {
      window.PlantUMLCore.renderToString(
        lines,
        resolve,
        function (message) {
          reject(new Error(message));
        }
      );
    });
  }

  function renderBlock(block) {
    var diagramText = block.textContent;
    var lines = diagramText.split(/\r\n|\r|\n/);
    return renderSource(lines).then(function (svg) {
      block.innerHTML = svg;
    });
  }

  /*
   * SysML diagrams.
   */

  // The inverse of encode_script_text() in plantuml_diagram.py.
  function decodeScriptText(text) {
    return text.replace(/\\u00(3C|5C)/g, function (match, code) {
      return code === "3C" ? "<" : "\\";
    });
  }

  // Splits data-sysml-options into words; key="a value" keeps its spaces.
  function parseOptions(text) {
    var words = (text || "").match(/(?:[^\s"]+|"[^"]*")+/g) || [];
    return words.map(function (word) {
      return word.replace(/"/g, "");
    });
  }

  function findSources(setId) {
    var containers = document.querySelectorAll("div.sysml_sources");
    for (var i = 0; i < containers.length; i++) {
      if (containers[i].getAttribute("data-sysml-set") !== setId) {
        continue;
      }
      var names = [];
      var texts = [];
      var scripts = containers[i].querySelectorAll(
        'script[type="text/sysml"]'
      );
      for (var j = 0; j < scripts.length; j++) {
        names.push(scripts[j].getAttribute("data-name"));
        texts.push(decodeScriptText(scripts[j].textContent));
      }
      return { names: names, texts: texts };
    }
    return null;
  }

  function sysmlToPlantUml(sources, options) {
    var result = null;
    var failure = null;
    // Synchronous: one of the callbacks runs before the call returns.
    window.PlantUMLCore.sysmlToPlantUml(
      sources.names,
      sources.texts,
      options,
      function (source) {
        result = source;
      },
      function (message) {
        failure = message;
      }
    );
    if (failure !== null || result === null) {
      throw new Error(failure || "sysmlToPlantUml returned nothing");
    }
    return result;
  }

  function showError(block, message) {
    var error = document.createElement("pre");
    error.className = "sysml_diagram__error";
    error.setAttribute("data-testid", "sysml-diagram-error");
    error.textContent =
      "SysML diagram (" +
      (block.getAttribute("data-sysml-options") || "no options") +
      "): " +
      message;
    block.replaceChildren(error);
  }

  function renderSysMLBlock(block) {
    block.setAttribute("data-processed", "true");
    var setId = block.getAttribute("data-sysml-set");
    var sources = findSources(setId);
    var source;
    try {
      if (sources === null) {
        throw new Error("the SysML files of " + setId + " are not on the page");
      }
      if (typeof window.PlantUMLCore.sysmlToPlantUml !== "function") {
        throw new Error("the PlantUML engine has no SysML import");
      }
      source = sysmlToPlantUml(
        sources,
        parseOptions(block.getAttribute("data-sysml-options"))
      );
    } catch (error) {
      showError(block, error.message);
      return Promise.resolve();
    }
    var lines = ["@startuml"].concat(source.split("\n"), ["@enduml"]);
    return renderSource(lines).then(
      function (svg) {
        block.innerHTML = svg;
      },
      function (error) {
        showError(block, error.message);
      }
    );
  }

  var lazyObserver = null;

  function observeLazyBlock(block) {
    if (!("IntersectionObserver" in window)) {
      return renderSysMLBlock(block);
    }
    if (lazyObserver === null) {
      lazyObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) {
              return;
            }
            lazyObserver.unobserve(entry.target);
            renderSysMLBlock(entry.target).catch(console.error);
          });
        },
        { rootMargin: "400px" }
      );
    }
    block.setAttribute("data-processed", "pending");
    lazyObserver.observe(block);
    return Promise.resolve();
  }

  async function renderPlantUMLBlocks() {
    // "data-processed" mirrors Mermaid's own marker: it lets repeated
    // calls (e.g. after a Turbo Stream node update) skip diagrams that are
    // already rendered, since their pre.plantuml text content has been
    // replaced by rendered SVG markup and re-rendering it would fail.
    var blocks = document.querySelectorAll(
      "pre.plantuml:not([data-processed])"
    );
    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i];
      await renderBlock(block);
      block.setAttribute("data-processed", "true");
    }
    var sysmlBlocks = document.querySelectorAll(
      "div.sysml_diagram:not([data-processed])"
    );
    for (var k = 0; k < sysmlBlocks.length; k++) {
      if (sysmlBlocks[k].hasAttribute("data-sysml-lazy")) {
        await observeLazyBlock(sysmlBlocks[k]);
      } else {
        await renderSysMLBlock(sysmlBlocks[k]);
      }
    }
  }

  window.strictdocRenderPlantUML = renderPlantUMLBlocks;
})();
