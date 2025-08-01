"use strict";
console.info("section1.js is loading ...");
const data = [
    {"SRC_ID": 0, "DST_ID": 1, }
]

/*******************Test tableau nodetables*******************/
document.addEventListener("DOMContentLoaded", () => {
    const tableWrapper = document.getElementById("table-wrapper");
    const pagination = document.getElementById("pagination");
    const pageTitle = document.getElementById("page-title");
    let grid = null;
  
    function loadPage(page = 1) {
        fetch(`/section1/data?page=${page}`)
          .then(res => res.json())
          .then(json => {
            const users = json.data;
            const currentPage = json.current_page;
            const totalPages = json.total_pages;
            const columns = json.columns;
      
            pageTitle.textContent = `Utilisateurs (page ${currentPage})`;
      
            const rows = users.map(u => columns.map(col => u[col]));
      
            if (grid) {
              grid.updateConfig({
                columns: columns,
                data: rows
              }).forceRender();
            } else {
              grid = new gridjs.Grid({
                columns: columns,
                data: rows,
                pagination: false,
                search: false,
                sort: false
              }).render(tableWrapper);
            }
      
            renderPagination(currentPage, totalPages);
          });
      }
      
  
    function renderPagination(current, total) {
      pagination.innerHTML = '';
      for (let i = 1; i <= total; i++) {
        const btn = document.createElement("button");
        btn.textContent = i;
        btn.disabled = (i === current);
        btn.addEventListener("click", () => loadPage(i));
        pagination.appendChild(btn);
      }
    }
  
    loadPage(); // init
  });

console.info("... script.js is loaded");
