const out = document.getElementById("out");

function showGreeting() {
  out.innerHTML = "Hi " + decodeURIComponent(location.hash.slice(1));
}

function showGreetingSafe() {
  out.textContent = "Hi " + decodeURIComponent(location.hash.slice(1));
}

showGreeting();
showGreetingSafe();
