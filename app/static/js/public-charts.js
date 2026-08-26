(function () {
  "use strict";

  var colors = ["#0369a1", "#047857", "#b45309", "#7c3aed", "#be123c", "#0e7490"];
  var textColor = "#0f172a";
  var mutedColor = "#475569";
  var gridColor = "#cbd5e1";

  function prepareCanvas(canvas) {
    var width = Math.max(canvas.clientWidth, 240);
    var height = Math.max(canvas.clientHeight, 220);
    var ratio = Math.min(window.devicePixelRatio || 1, 2);
    var pixelWidth = Math.round(width * ratio);
    var pixelHeight = Math.round(height * ratio);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    var context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.lineCap = "round";
    context.lineJoin = "round";
    return { context: context, width: width, height: height };
  }

  function font(context, size, weight) {
    context.font = (weight || 400) + " " + size + "px Inter, ui-sans-serif, system-ui, sans-serif";
    context.fillStyle = textColor;
  }

  function shortLabel(value, limit) {
    var label = String(value || "Not set");
    return label.length > limit ? label.slice(0, limit - 1) + "…" : label;
  }

  function emptyState(context, width, height) {
    font(context, 14, 600);
    context.fillStyle = mutedColor;
    context.textAlign = "center";
    context.fillText("No published data yet", width / 2, height / 2);
  }

  function drawBars(canvas, rows) {
    var frame = prepareCanvas(canvas);
    var context = frame.context;
    var width = frame.width;
    var height = frame.height;
    if (!rows.length || !rows.some(function (row) { return (Number(row.value) || 0) > 0; })) {
      return emptyState(context, width, height);
    }

    var left = 42;
    var right = 16;
    var top = 22;
    var bottom = 54;
    var chartWidth = width - left - right;
    var chartHeight = height - top - bottom;
    var maximum = Math.max.apply(null, rows.map(function (row) { return Number(row.value) || 0; }).concat([1]));
    var slot = chartWidth / rows.length;
    var barWidth = Math.min(slot * 0.58, 52);

    context.strokeStyle = gridColor;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(left, top);
    context.lineTo(left, top + chartHeight);
    context.lineTo(left + chartWidth, top + chartHeight);
    context.stroke();

    rows.forEach(function (row, index) {
      var value = Number(row.value) || 0;
      var barHeight = chartHeight * value / maximum;
      var x = left + slot * index + (slot - barWidth) / 2;
      var y = top + chartHeight - barHeight;
      context.fillStyle = colors[index % colors.length];
      context.fillRect(x, y, barWidth, barHeight);
      font(context, 12, 600);
      context.textAlign = "center";
      context.fillText(String(value), x + barWidth / 2, Math.max(y - 7, 13));
      font(context, 11, 400);
      context.fillStyle = mutedColor;
      context.fillText(shortLabel(row.label, 13), x + barWidth / 2, top + chartHeight + 20);
    });
  }

  function drawDonut(canvas, rows) {
    var frame = prepareCanvas(canvas);
    var context = frame.context;
    var width = frame.width;
    var height = frame.height;
    var total = rows.reduce(function (sum, row) { return sum + (Number(row.value) || 0); }, 0);
    if (!rows.length || total <= 0) return emptyState(context, width, height);

    var legendHeight = Math.min(rows.length, 4) * 22;
    var radius = Math.max(Math.min(width, height - legendHeight) * 0.27, 48);
    var centerX = width / 2;
    var centerY = (height - legendHeight) / 2 + 4;
    var start = -Math.PI / 2;
    rows.forEach(function (row, index) {
      var angle = Math.PI * 2 * (Number(row.value) || 0) / total;
      context.beginPath();
      context.strokeStyle = colors[index % colors.length];
      context.lineWidth = Math.max(radius * 0.42, 24);
      context.arc(centerX, centerY, radius, start, start + angle);
      context.stroke();
      start += angle;
    });
    font(context, 17, 700);
    context.textAlign = "center";
    context.fillText(String(total), centerX, centerY + 6);

    font(context, 11, 500);
    rows.slice(0, 4).forEach(function (row, index) {
      var legendY = height - legendHeight + 16 + index * 22;
      context.fillStyle = colors[index % colors.length];
      context.fillRect(20, legendY - 9, 10, 10);
      context.fillStyle = mutedColor;
      context.textAlign = "left";
      context.fillText(shortLabel(row.label, 24) + " · " + (Number(row.value) || 0), 38, legendY);
    });
  }

  function drawLine(canvas, rows) {
    var frame = prepareCanvas(canvas);
    var context = frame.context;
    var width = frame.width;
    var height = frame.height;
    if (!rows.length) return emptyState(context, width, height);

    var left = 44;
    var right = 18;
    var top = 24;
    var bottom = 42;
    var chartWidth = width - left - right;
    var chartHeight = height - top - bottom;
    var maximum = Math.max.apply(null, rows.map(function (row) { return Number(row.value) || 0; }).concat([1]));
    var points = rows.map(function (row, index) {
      return {
        x: left + (rows.length === 1 ? chartWidth / 2 : chartWidth * index / (rows.length - 1)),
        y: top + chartHeight - chartHeight * (Number(row.value) || 0) / maximum,
        value: Number(row.value) || 0,
        label: row.label,
      };
    });

    context.strokeStyle = gridColor;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(left, top);
    context.lineTo(left, top + chartHeight);
    context.lineTo(left + chartWidth, top + chartHeight);
    context.stroke();

    context.strokeStyle = colors[0];
    context.lineWidth = 3;
    context.beginPath();
    points.forEach(function (point, index) {
      if (index === 0) context.moveTo(point.x, point.y);
      else context.lineTo(point.x, point.y);
    });
    context.stroke();

    points.forEach(function (point, index) {
      context.fillStyle = colors[0];
      context.beginPath();
      context.arc(point.x, point.y, 4, 0, Math.PI * 2);
      context.fill();
      font(context, 11, 600);
      context.textAlign = "center";
      context.fillText(String(point.value), point.x, Math.max(point.y - 10, 12));
      font(context, 11, 400);
      context.fillStyle = mutedColor;
      context.fillText(shortLabel(point.label, 14), point.x, top + chartHeight + 21);
    });
  }

  function keepResponsive(render) {
    render();
    if ("ResizeObserver" in window) {
      var observer = new ResizeObserver(function () { render(); });
      return function (canvas) { observer.observe(canvas); };
    }
    var scheduled = false;
    window.addEventListener("resize", function () {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(function () {
        render();
        scheduled = false;
      });
    });
    return function () {};
  }

  function renderPublicCharts(dataUrl) {
    var campusCanvas = document.getElementById("campusChart");
    var programCanvas = document.getElementById("programChart");
    var participationCanvas = document.getElementById("participationChart");
    if (!campusCanvas && !programCanvas && !participationCanvas) {
      return;
    }
    fetch(dataUrl)
      .then(function (response) {
        if (!response.ok) throw new Error("Public analytics could not be loaded.");
        return response.json();
      })
      .then(function (data) {
        var render = function () {
          if (campusCanvas) drawBars(campusCanvas, data.events_per_campus || []);
          if (programCanvas) drawDonut(programCanvas, data.program_split || []);
          if (participationCanvas) drawLine(participationCanvas, data.participation_trend || []);
        };
        var observe = keepResponsive(render);
        [campusCanvas, programCanvas, participationCanvas].filter(Boolean).forEach(observe);
      })
      .catch(function () {
        [campusCanvas, programCanvas, participationCanvas].filter(Boolean).forEach(function (canvas) {
          var frame = prepareCanvas(canvas);
          emptyState(frame.context, frame.width, frame.height);
        });
      });
  }

  window.OIAPublicCharts = { render: renderPublicCharts };

  document.addEventListener("DOMContentLoaded", function () {
    var dataUrl = document.body.getAttribute("data-analytics-url");
    if (dataUrl) {
      renderPublicCharts(dataUrl);
    }
  });
})();
