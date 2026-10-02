import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import api from "./api/axios";
import {
  createIncident,
  deleteIncident,
  fetchIncidents,
  updateIncident,
} from "./features/incidents/incidentsSlice";
import { fetchRoutes } from "./features/routes/routesSlice";
import "./index.css";

const PAGE_SIZE = 25;

const emptyIncident = {
  incidentCode: "",
  incidentTitle: "",
  routeLine: "",
  routeId: "",
  submitterEmail: "",
  description: "",
  category: "delay",
  passengersAffected: 0,
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
              <Link to="/update">Update Incident</Link>
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
            path="/update"
            element={<IncidentForm user={user} mode="update" />}
          />
          <Route
            path="/update/:id"
            element={<IncidentForm user={user} mode="update" />}
          />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

function Login({ setUser }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    </section>
  );
}

function Home({ user }) {
  const dispatch = useDispatch();
  const { items, status, error, page } = useSelector(
    (state) => state.incidents,
  );
  const [pageNumber, setPageNumber] = useState(0);

  useEffect(() => {
    if (user) {
      dispatch(
        fetchIncidents({
          skip: pageNumber * PAGE_SIZE,
          limit: PAGE_SIZE,
        }),
      );
    }
  }, [dispatch, user, pageNumber]);

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

  async function removeIncident(id) {
    await dispatch(deleteIncident(id));
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <h2>Incident Records</h2>
          <p>Showing page {pageNumber + 1}; 25 records maximum.</p>
        </div>
        <Link className="button" to="/create">
          Create Incident
        </Link>
      </div>

      {error && <p className="error">{error}</p>}
      {status === "loading" && <p className="loading">Loading incidents...</p>}

      {status !== "loading" && items.length === 0 ? (
        <div className="card">
          <p>No incidents found.</p>
        </div>
      ) : (
        <div className="incident-list">
          {items.map((incident) => (
            <article className="card" key={incident.id}>
              <h3>{incident.incidentTitle}</h3>
              <p>
                <strong>Code:</strong> {incident.incidentCode}
              </p>
              <p>
                <strong>Route:</strong> {incident.routeLine}
              </p>
              <p>
                <strong>Category:</strong> {incident.category}
              </p>
              <p>{incident.description}</p>

              <div className="actions">
                <Link className="button secondary" to={`/update/${incident.id}`}>
                  Update
                </Link>
                <button
                  className="button danger"
                  onClick={() => removeIncident(incident.id)}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="actions">
        <button
          className="button secondary"
          disabled={pageNumber === 0 || status === "loading"}
          onClick={() => setPageNumber((current) => current - 1)}
        >
          Previous page
        </button>
        <button
          className="button secondary"
          disabled={items.length < page.limit || status === "loading"}
          onClick={() => setPageNumber((current) => current + 1)}
        >
          Next page
        </button>
      </div>
    </section>
  );
}

function IncidentForm({ user, mode }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { id } = useParams();
  const editing = mode === "update";
  const incidents = useSelector((state) => state.incidents.items);
  const routes = useSelector((state) => state.routes.items);
  const routeError = useSelector((state) => state.routes.error);
  const [selectedId, setSelectedId] = useState(id || "");
  const [data, setData] = useState({ ...emptyIncident });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    dispatch(fetchRoutes());
  }, [dispatch, user]);

  useEffect(() => {
    if (!user || !editing || !selectedId) return;

    const localIncident = incidents.find(
      (incident) => incident.id === Number(selectedId),
    );
    const load = localIncident
      ? Promise.resolve({ data: localIncident })
      : api.get(`/incidents/${selectedId}`);

    load
      .then((response) => {
        setData({
          incidentCode: response.data.incidentCode,
          incidentTitle: response.data.incidentTitle,
          routeLine: response.data.routeLine,
          routeId: String(response.data.routeId),
          submitterEmail: response.data.submitterEmail,
          description: response.data.description,
          category: response.data.category,
          passengersAffected: response.data.passengersAffected,
          termsAccepted: true,
        });
      })
      .catch((err) =>
        setError(err.response?.data?.detail || "Could not load this incident."),
      );
  }, [user, editing, selectedId, incidents]);

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

  function selectRoute(event) {
    const routeId = event.target.value;
    const route = routes.find((item) => item.id === Number(routeId));
    setData((current) => ({
      ...current,
      routeId,
      routeLine: route?.routeName || current.routeLine,
    }));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");

    const payload = {
      incidentCode: data.incidentCode,
      incidentTitle: data.incidentTitle,
      routeLine: data.routeLine,
      routeId: Number(data.routeId),
      submitterEmail: data.submitterEmail,
      description: data.description,
      category: data.category,
      passengersAffected: Number(data.passengersAffected),
      termsAccepted: Boolean(data.termsAccepted),
    };

    try {
      if (editing) {
        await dispatch(updateIncident({ id: selectedId, payload })).unwrap();
      } else {
        await dispatch(createIncident(payload)).unwrap();
      }
      navigate("/");
    } catch (err) {
      setError(typeof err === "string" ? err : "Could not save incident.");
    }
  }

  return (
    <section className="card form-card">
      <h2>{editing ? "Update Incident" : "Create Incident"}</h2>
      {error && <p className="error">{error}</p>}
      {routeError && <p className="error">{routeError}</p>}

      {editing && (
        <>
          <label>Incident ID</label>
          <select
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
            required
          >
            <option value="">Select an incident ID</option>
            {incidents.map((incident) => (
              <option key={incident.id} value={incident.id}>
                {incident.id} - {incident.incidentCode}
              </option>
            ))}
          </select>
        </>
      )}

      <form onSubmit={submit}>
        <label>Incident code</label>
        <input
          name="incidentCode"
          value={data.incidentCode}
          onChange={updateField}
          placeholder="INC-005001"
          pattern="INC-[0-9]{6}"
          required
        />

        <label>Incident title</label>
        <input
          name="incidentTitle"
          value={data.incidentTitle}
          onChange={updateField}
          required
          minLength="3"
        />

        <label>Route</label>
        <select value={data.routeId} onChange={selectRoute} required>
          <option value="">Select a route</option>
          {routes.map((route) => (
            <option key={route.id} value={route.id}>
              {route.routeCode} - {route.routeName}
            </option>
          ))}
        </select>

        <label>Submitter email</label>
        <input
          name="submitterEmail"
          type="email"
          value={data.submitterEmail || user.email}
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
          <option value="infrastructure-issue">Infrastructure issue</option>
        </select>

        <label>Passengers affected</label>
        <input
          name="passengersAffected"
          type="number"
          min="0"
          value={data.passengersAffected}
          onChange={updateField}
        />

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

export default App;
