"use strict";
console.info("script.js is loading ...");

/*******************index.html*******************/
const navButtons = document.querySelectorAll("nav a");

navButtons.forEach((navButton) => {
    navButton.addEventListener("click", (event) => {
        event.preventDefault();
        window.location.href = navButton.getAttribute("href");
    });
});

console.info("... script.js is loaded");
