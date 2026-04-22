const revealTargets = document.querySelectorAll("[data-reveal], [data-depth]");

const revealObserver = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    }
  },
  { threshold: 0.18 }
);

for (const target of revealTargets) {
  revealObserver.observe(target);
}
