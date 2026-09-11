const incidentForm = document.querySelector("#incidentForm");
const updateForm = document.querySelector("#updateForm");
const deleteForm = document.querySelector("#deleteForm");
const searchForm = document.querySelector("#searchForm");

const searchQuery = document.querySelector("#searchQuery");
const clearSearchButton = document.querySelector("#clearSearch");

const incidentList = document.querySelector("#incidentList");
const recordCount = document.querySelector("#recordCount");

const loadingState = document.querySelector("#loadingState");
const emptyState = document.querySelector("#emptyState");
const errorState = document.querySelector("#errorState");
const errorMessage = document.querySelector("#errorMessage");


const wait = (milliseconds) =>
    new Promise((resolve) => window.setTimeout(resolve, milliseconds));


const hideAllResults = () => {
    loadingState.hidden = true;
    emptyState.hidden = true;
    errorState.hidden = true;
    incidentList.hidden = true;
};


const showLoading = (message = "Loading incident records...") => {
    hideAllResults();
    loadingState.textContent = message;
    loadingState.hidden = false;
};


const showError = (message) => {
    hideAllResults();
    errorMessage.textContent = message;
    errorState.hidden = false;
    recordCount.textContent = "Unavailable";
};


const formatCategory = (category) =>
    category
        .split("-")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ");


const addDetail = (card, label, value) => {
    const paragraph = document.createElement("p");
    const strong = document.createElement("strong");

    strong.textContent = `${label}: `;
    paragraph.append(strong, document.createTextNode(value));
    card.append(paragraph);
};


const renderIncidents = (incidents) => {
    hideAllResults();
    incidentList.replaceChildren();

    const count = incidents.length;
    recordCount.textContent = `${count} ${count === 1 ? "record" : "records"}`;

    if (count === 0) {
        emptyState.hidden = false;
        return;
    }

    incidents.forEach((incident) => {
        const card = document.createElement("article");
        card.className = "incident-card";

        const heading = document.createElement("h3");
        heading.textContent = `#${incident.id}: ${incident.incidentTitle}`;
        card.append(heading);

        addDetail(card, "Route", incident.routeLine);
        addDetail(card, "Description", incident.description);
        addDetail(card, "Submitter", incident.submitterEmail);

        const date = document.createElement("p");
        date.className = "incident-meta";
        date.textContent =
            `Submitted: ${new Date(incident.submissionDate).toLocaleString()}`;
        card.append(date);

        const category = document.createElement("span");
        category.className = "category-badge";
        category.textContent = formatCategory(incident.category);
        card.append(category);

        incidentList.append(card);
    });

    incidentList.hidden = false;
};


const loadIncidents = async (query = "") => {
    showLoading();
    if (
    new URLSearchParams(window.location.search).get("demo") === "loading"
    ) {
    return;
    }

    try {
        const apiParameters = new URLSearchParams();

        if (query.trim()) {
            apiParameters.set("q", query.trim());
        }

        const pageParameters = new URLSearchParams(window.location.search);

        if (pageParameters.get("demo") === "error") {
            apiParameters.set("simulate_error", "true");
        }

        const apiUrl = apiParameters.toString()
            ? `/api/incidents?${apiParameters.toString()}`
            : "/api/incidents";

        const [response] = await Promise.all([
            fetch(apiUrl),
            wait(500),
        ]);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));

            throw new Error(
                errorData.detail || `Request failed with status ${response.status}.`
            );
        }

        const incidents = await response.json();
        renderIncidents(incidents);
    } catch (error) {
        showError(error.message || "Please try again.");
    }
};


searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    loadIncidents(searchQuery.value);
});


clearSearchButton.addEventListener("click", () => {
    searchQuery.value = "";
    loadIncidents();
});


incidentForm.addEventListener("submit", (event) => {
    const description = document.querySelector("#description").value.trim();
    const termsAccepted = document.querySelector("#termsAccepted").checked;

    if (description.length <= 25) {
        event.preventDefault();
        alert("The incident description must contain more than 25 characters.");
        return;
    }

    if (!termsAccepted) {
        event.preventDefault();
        alert("You must agree to the terms and conditions.");
        return;
    }

    if (!incidentForm.checkValidity()) {
        event.preventDefault();
        incidentForm.reportValidity();
        return;
    }

    const formData = new FormData(incidentForm);
    const incidentData = Object.fromEntries(formData.entries());

    incidentData.termsAccepted = termsAccepted;
    incidentData.submissionDate = new Date().toISOString();

    console.log("New incident submission:", incidentData);
    showLoading("Saving the new incident...");
});


updateForm.addEventListener("submit", () => {
    showLoading("Updating incident ID 1...");
});


deleteForm.addEventListener("submit", (event) => {
    const confirmed = window.confirm(
        "Delete the incident with the highest ID?"
    );

    if (!confirmed) {
        event.preventDefault();
        return;
    }

    showLoading("Deleting the highest-ID incident...");
});


const redirectedError =
    new URLSearchParams(window.location.search).get("error");

if (redirectedError) {
    showError(redirectedError);
} else {
    loadIncidents();
}