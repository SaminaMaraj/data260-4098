const form = document.querySelector("#incidentForm");

const hasValidDescription = (text) => text.trim().length > 25;
const createSubmissionCounter = () => {
    let count = 0;

    return () => {
        count += 1;
        return count;
    };
};

const countSuccessfulSubmission = createSubmissionCounter();

form.addEventListener("submit", (event) => {
    event.preventDefault();

    const description = document.querySelector("#description").value;
    const termsAccepted = document.querySelector("#termsAccepted").checked;

    if (!hasValidDescription(description)) {
        alert("The incident description must contain more than 25 characters.");
        return;
    }

    if (!termsAccepted) {
        alert("You must agree to the terms and conditions.");
        return;
    }
        if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    const incidentTitle = document.querySelector("#incidentTitle").value.trim();
    const routeLine = document.querySelector("#routeLine").value.trim();
    const submitterEmail = document.querySelector("#submitterEmail").value.trim();
    const category = document.querySelector("#category").value;

    const incidentData = {
        incidentTitle,
        routeLine,
        submitterEmail,
        description: description.trim(),
        category,
        termsAccepted
    };

    const jsonString = JSON.stringify(incidentData);
    console.log(jsonString);
        const parsedData = JSON.parse(jsonString);

    const {
        incidentTitle: parsedIncidentTitle,
        submitterEmail: parsedSubmitterEmail
    } = parsedData;

    console.log("Incident title:", parsedIncidentTitle);
    console.log("Submitter email:", parsedSubmitterEmail);
        const finalIncidentData = {
        ...parsedData,
        submissionDate: new Date().toISOString()
    };

    console.log("Final incident data:", JSON.stringify(finalIncidentData));
    const successfulCount = countSuccessfulSubmission();
    console.log("Successful submissions:", successfulCount);
});
