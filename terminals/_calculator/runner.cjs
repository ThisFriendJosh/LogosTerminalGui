/* Reuse the calculators' original pure engines; never evaluate user input as code. */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadEngine(directory, engine) {
  global.window = globalThis;
  if (!global.crypto) global.crypto = require("node:crypto").webcrypto;
  const html = fs.readFileSync(path.join(directory, "app.html"), "utf8");
  const statScripts = new Set([
    "traceValueFormat", "gammaFunctions", "normalQuantile", "studentT", "chiSquare",
    "seededRandom", "parser", "quantitative", "qualitative", "tInterval", "medianInterval",
    "sdInterval", "wilson", "findings", "correlation", "crossTab", "confidenceLevel"
  ]);
  let loaded = 0;
  for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi)) {
    const source = match[1];
    const marker = source.match(/^\s*\/\* ([\w/]+\.js) \*\//);
    if (!marker) continue;
    const file = marker[1];
    const selected = file.startsWith("contracts/") || (engine === "cryptocalc"
      ? /^scripts\/(ops\/|core\/(byteFormat|registry|recipeRunner)\.js$)/.test(file)
      : /^scripts\/([^/]+)\.js$/.test(file) && statScripts.has(path.basename(file, ".js")));
    if (selected) {
      vm.runInThisContext(source, {filename: file});
      loaded++;
    }
  }
  if (!loaded) throw new Error("Calculator engine scripts are missing from app.html");
}

function object(value, message) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  return value;
}

async function cryptoExecute(action, text) {
  const C = window.CryptoCalc;
  if (action === "operations") {
    const needle = text.trim().toLowerCase();
    return C.Registry.list().filter(d => (d.id + " " + d.name).toLowerCase().includes(needle))
      .map(d => d.id + " - " + d.name + "\n  " + d.hint +
        (d.params.length ? "\n  args: " + JSON.stringify(C.Registry.defaults(d.id)) : "")).join("\n\n") || "No matching operations.";
  }
  if (action !== "run") throw new Error("Unknown CryptoCalc action");
  let request;
  if (text.trimStart().startsWith("{")) request = object(JSON.parse(text), "Use a JSON object");
  else {
    const match = text.match(/^\s*([a-z][a-z0-9_]*)(?:[ \t]|\r?\n|$)([\s\S]*)$/);
    if (!match) throw new Error("Use: to_base64 Hello, or choose Help for recipe examples.");
    request = {input: match[2], steps: [{op: match[1]}]};
  }
  if (typeof request.input !== "string") throw new Error("Recipe input must be a string");
  if (!Array.isArray(request.steps) || !request.steps.length || request.steps.length > 64)
    throw new Error("Supply between 1 and 64 recipe steps");
  request.steps.forEach(s => {
    object(s, "Each recipe step must be an object");
    if (typeof s.op !== "string" || !C.Registry.get(s.op)) throw new Error("Unknown operation: " + s.op);
    if (s.args !== undefined) object(s.args, "Step args must be an object");
    if (s.disabled !== undefined && typeof s.disabled !== "boolean") throw new Error("disabled must be true or false");
  });
  const run = await C.RecipeRunner.run({steps: request.steps}, C.ByteFormat.fromText(request.input));
  if (!run.ok) {
    const failed = run.steps.find(s => s.status === "failed");
    throw new Error(failed.name + ": " + failed.problem.message);
  }
  const output = run.final.isText ? C.ByteFormat.utf8Decode(run.final.bytes) : C.ByteFormat.toHex(run.final.bytes);
  return output + "\n\n" + run.steps.map(s => s.name + ": " + s.inputBytes + " -> " + s.outputBytes + " bytes" +
    (s.status === "off" ? " (disabled)" : "") + (s.note ? "\n" + s.note : "")).join("\n") +
    (run.final.isText ? "" : "\nBinary output displayed as hexadecimal.");
}

function format(value) {
  return value === null || value === undefined ? "not defined" :
    typeof value === "number" ? String(Number(value.toPrecision(10))) : String(value);
}

function statsExecute(action, text) {
  const S = window.StatCalc2;
  if (!["analyze", "json"].includes(action)) throw new Error("Unknown StatCalc action");
  let request = {data: text, confidence: 95};
  if (text.trimStart().startsWith("{")) request = object(JSON.parse(text), "Use a JSON object");
  if (typeof request.data !== "string" || !request.data.trim()) throw new Error("Paste numbers or CSV data first");
  const percent = request.confidence === undefined ? 95 : request.confidence;
  const rules = S.Contracts.ConfidenceLevels;
  if (typeof percent !== "number" || !Number.isFinite(percent) || percent < rules.customMin || percent > rules.customMax)
    throw new Error("Confidence must be a number from " + rules.customMin + " to " + rules.customMax);
  const parsed = S.Parser.parseFile(request.data, "terminal.csv");
  if (!parsed.ok) throw new Error(parsed.problem.message);
  const dataset = parsed.value;
  if (dataset.columns.length > 20) throw new Error("Use up to 20 columns here; use the full calculator for larger tables.");
  const level = S.ConfidenceLevel.fromPercent(percent, "custom");
  const reports = dataset.columns.map((column, index) => {
    let summary = null;
    const intervals = [];
    if (column.kind === "quantitative") {
      summary = S.Quantitative.summarize(column);
      [S.TInterval.run(summary, level), summary.n ? S.MedianInterval.run(column, summary, level) : null,
        S.SdInterval.run(summary, level)].forEach(iv => { if (iv) intervals.push(iv); });
    } else if (column.kind === "qualitative") {
      summary = S.Qualitative.summarize(column);
      summary.categories.forEach(c => intervals.push(S.Wilson.run(c.count, summary.n, level, column.name, c.category)));
    }
    const report = {columnNumber: index + 1, column, summary, intervals};
    report.findings = S.Findings.write(report, level);
    return report;
  });
  const pairs = [];
  for (let i = 0; i < dataset.columns.length; i++) {
    for (let j = i + 1; j < dataset.columns.length; j++) {
      const a = dataset.columns[i], b = dataset.columns[j];
      if (a.kind === "quantitative" && b.kind === "quantitative") pairs.push(S.Correlation.run(a, b, level));
      if (a.kind === "qualitative" && b.kind === "qualitative") pairs.push(S.CrossTab.run(a, b));
    }
  }
  if (action === "json") return JSON.stringify({dataset, level, reports, pairs}, null, 2);
  const lines = ["StatCalc2 | " + dataset.rowCount + " rows | " + percent + "% confidence"];
  reports.forEach(report => {
    const {column, summary, intervals, findings} = report;
    lines.push("", column.name + " (" + column.kind + ")");
    if (summary && column.kind === "quantitative") {
      for (const key of ["n", "sum", "mean", "median", "min", "max", "q1", "q3", "variance", "sd", "se", "iqr", "skewness"])
        lines.push("  " + key + ": " + format(summary[key]));
    } else if (summary) {
      lines.push("  n: " + summary.n);
      summary.categories.forEach(c => lines.push("  " + c.category + ": " + c.count + " (" + format(c.share * 100) + "%)"));
    }
    intervals.forEach(iv => lines.push("  " + (iv.label || iv.method) +
      (iv.category ? " [" + iv.category + "]" : "") + ": " + format(iv.lower) + " to " + format(iv.upper) +
      (iv.problem ? " - " + (iv.problem.message || iv.problem) : "")));
    lines.push("  " + findings.verdict);
    findings.points.forEach(p => lines.push("  " + p.text));
  });
  pairs.forEach(pair => {
    lines.push("", pair.kind === "correlation" ? pair.xName + " / " + pair.yName : pair.rowName + " / " + pair.colName);
    pair.trace.outputs.forEach(o => lines.push("  " + o.label + ": " + format(o.value)));
    if (pair.smallExpected) lines.push("  Caution: " + pair.smallExpected + " expected cell counts are below 5.");
  });
  return lines.join("\n");
}

async function main() {
  if (Number(process.versions.node.split(".")[0]) < 22) throw new Error("Node.js 22 or newer is required");
  const directory = path.resolve(process.argv[2]);
  const manifest = JSON.parse(fs.readFileSync(path.join(directory, "terminal.json"), "utf8"));
  const input = JSON.parse(fs.readFileSync(0, "utf8"));
  const engine = manifest.extensions.calculator.engine;
  loadEngine(directory, engine);
  const text = engine === "cryptocalc" ? await cryptoExecute(process.argv[3], input.text) : statsExecute(process.argv[3], input.text);
  if (text.length > 100_000) throw new Error("Result exceeds the terminal display limit. Use a smaller input or Open full calculator.");
  process.stdout.write(JSON.stringify({text}));
}
main().catch(error => process.stdout.write(JSON.stringify({error: error.message})));
