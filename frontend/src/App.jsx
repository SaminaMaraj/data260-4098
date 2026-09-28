import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import axios from "axios";
import "./index.css";

const api = axios.create({
  baseURL: "http://localhost:8498/api/hw4",
  withCredentials: true,
});

const emptyIncident = {
  incidentTitle: "",
  routeLine: "",
  submitterEmail: "",
  description: "",
  category: "delay",
  termsAccepted: false,
};

function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    api
      .get("/auth/me")
      .then((response) => setUser(response.data))
      .catch(() => setUser(null))
      .finally(() => setCheckingSession(false));
  }, []);

  async function logout() {
    await api.post("/auth/logout");
    setUser(null);
  }

  if (checkingSession) {
    return <p className="loading">Checking login session...</p>;
  }

  return (
    <BrowserRouter>
      <header>
        <h1>Transit Incident Hub</h1>
        <nav>
          <Link to="/">Home</Link>
          {user ? (
            <>
              <Link to="/create">Create Incident</Link>
              <span>Signed in as {user.name}</span>
              <button onClick={logout}>Log out</button>
            </>
          ) : (
            <Link to="/login">Log in</Link>
          )}
        </nav>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home user={user} />} />
          <Route path="/login" element={<Login setUser={setUser} />} />
          <Route
            path="/create"
            element={<IncidentForm user={user} mode="create" />}
          />
          <Route
            path="/update/:id"
            element={<IncidentForm user={user} mode="update" />}
          />
          <Route
            path="/delete/:id"
            element={<DeleteIncident user={user} />}
          />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

function Home({ user }) {
  const [incidents, setIncidents] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;

    api
      .get("/incidents")
      .then((response) => setIncidents(response.data))
      .catch(() => setError("Could not load incidents."));
  }, [user]);

  if (!user) {
    return (
      <section className="card">
        <h2>Login required</h2>
        <p>Please log in to view and manage incident records.</p>
        <Link className="button" to="/login">
          Go to Login
        </Link>
      </section>
    );
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <h2>Incident Records</h2>
          <p>View, create, update, and delete transit incidents.</p>
        </div>
        <Link className="button" to="/create">
          Create Incident
        </Link>
      </div>

      {error && <p className="error">{error}</p>}

      {incidents.length === 0 ? (
        <div className="card">
          <p>No incidents found.</p>
        </div>
      ) : (
        <div className="incident-list">
          {incidents.map((incident) => (
            <article className="card" key={incident.id}>
              <h3>{incident.incidentTitle}</h3>
              <p>
                <strong>Route:</strong> {incident.routeLine}
              </p>
              <p>
                <strong>Category:</strong> {incident.category}
              </p>
              <p>{incident.description}</p>
              <p className="small">
                Submitted by {incident.submitterEmail}
              </p>

              <div className="actions">
                <Link className="button secondary" to={`/update/${incident.id}`}>
                  Update
                </Link>
                <Link className="button danger" to={`/delete/${incident.id}`}>
                  Delete
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Login({ setUser }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("samina.hw4@example.com");
  const [password, setPassword] = useState("Transit4098!");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");

    try {
      const response = await api.post("/auth/login", { email, password });
      setUser(response.data.user);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed.");
    }
  }

  return (
    <section className="card form-card">
      <h2>Log in</h2>

      {error && <p className="error">{error}</p>}

      <form onSubmit={submit}>
        <label>Email</label>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />

        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />

        <button className="button" type="submit">
          Log in
        </button>
      </form>

      <p className="small">
        Demo account: samina.hw4@example.com / Transit4098!
      </p>
    </section>
  );
}

function IncidentForm({ user, mode }) {
  const navigate = useNavigate();
  const { id } = useParams();
  const editing = mode === "update";

  const [data, setData] = useState({
    ...emptyIncident,
    submitterEmail: user?.email || "",
  });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user || !editing) return;

    api
      .get(`/incidents/${id}`)
      .then((response) => {
        setData({
          ...response.data,
          termsAccepted: true,
        });
      })
      .catch(() => setError("Could not load this incident."));
  }, [user, editing, id]);

  if (!user) {
    return (
      <section className="card">
        <h2>Login required</h2>
        <Link className="button" to="/login">
          Go to Login
        </Link>
      </section>
    );
  }

  function updateField(event) {
    const { name, value, type, checked } = event.target;
    setData((current) => ({
      ...current,
      [name]: type === "checkbox" ? checked : value,
    }));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");

    const payload = {
      incidentTitle: data.incidentTitle,
      routeLine: data.routeLine,
      submitterEmail: data.submitterEmail,
      description: data.description,
      category: data.category,
      termsAccepted: Boolean(data.termsAccepted),
    };

    try {
      if (editing) {
        await api.put(`/incidents/${id}`, payload);
      } else {
        await api.post("/incidents", payload);
      }

      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save incident.");
    }
  }

  return (
    <section className="card form-card">
      <h2>{editing ? "Update Incident" : "Create Incident"}</h2>

      {error && <p className="error">{error}</p>}

      <form onSubmit={submit}>
        <label>Incident title</label>
        <input
          name="incidentTitle"
          value={data.incidentTitle}
          onChange={updateField}
          required
          minLength="3"
        />

        <label>Route or line</label>
        <input
          name="routeLine"
          value={data.routeLine}
          onChange={updateField}
          required
          minLength="2"
        />

        <label>Submitter email</label>
        <input
          name="submitterEmail"
          type="email"
          value={data.submitterEmail}
          onChange={updateField}
          required
        />

        <label>Description</label>
        <textarea
          name="description"
          value={data.description}
          onChange={updateField}
          required
          minLength="26"
        />

        <label>Category</label>
        <select name="category" value={data.category} onChange={updateField}>
          <option value="delay">Delay</option>
          <option value="collision">Collision</option>
          <option value="service-suspension">Service suspension</option>
          <option value="infrastructure-issue">
            Infrastructure issue
          </option>
        </select>

        <label className="checkbox">
          <input
            type="checkbox"
            name="termsAccepted"
            checked={data.termsAccepted}
            onChange={updateField}
            required
          />
          I accept the terms and conditions.
        </label>

        <button className="button" type="submit">
          {editing ? "Save Changes" : "Create Incident"}
        </button>
      </form>
    </section>
  );
}

function DeleteIncident({ user }) {
  const navigate = useNavigate();
  const { id } = useParams();
  const [error, setError] = useState("");

  if (!user) {
    return (
      <section className="card">
        <h2>Login required</h2>
        <Link className="button" to="/login">
          Go to Login
        </Link>
      </section>
    );
  }

  async function confirmDelete() {
    try {
      await api.delete(`/incidents/${id}`);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not delete incident.");
    }
  }

  return (
    <section className="card">
      <h2>Delete Incident</h2>
      <p>Are you sure you want to delete incident #{id}?</p>

      {error && <p className="error">{error}</p>}

      <div className="actions">
        <button className="button danger" onClick={confirmDelete}>
          Delete
        </button>
        <Link className="button secondary" to="/">
          Cancel
        </Link>
      </div>
    </section>
  );
}

export default App;