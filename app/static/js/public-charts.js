(function () {
  "use strict";

  function renderPublicCharts(dataUrl) {
    var campusCanvas = document.getElementById("campusChart");
    var programCanvas = document.getElementById("programChart");
    var participationCanvas = document.getElementById("participationChart");
    if (!campusCanvas && !programCanvas && !participationCanvas) {
      return;
    }
    fetch(dataUrl)
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (campusCanvas) {
          new Chart(campusCanvas, {
            type: "bar",
            data: {
              labels: data.events_per_campus.map(function (row) { return row.label; }),
              datasets: [{ label: "Events per campus", data: data.events_per_campus.map(function (row) { return row.value; }) }],
            },
          });
        }
        if (programCanvas) {
          new Chart(programCanvas, {
            type: "doughnut",
            data: {
              labels: data.program_split.map(function (row) { return row.label; }),
              datasets: [{ data: data.program_split.map(function (row) { return row.value; }) }],
            },
          });
        }
        if (participationCanvas) {
          new Chart(participationCanvas, {
            type: "line",
            data: {
              labels: data.participation_trend.map(function (_, index) { return "Year " + (index + 1); }),
              datasets: [{ label: "Actual reach by academic year", data: data.participation_trend }],
            },
          });
        }
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
