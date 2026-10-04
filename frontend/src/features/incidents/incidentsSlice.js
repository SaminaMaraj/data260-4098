import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import api from "../../api/axios";

function errorMessage(error, fallback) {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
  }
  return detail || fallback;
}

export const fetchIncidents = createAsyncThunk(
  "incidents/fetchIncidents",
  async ({ q = "", skip = 0, limit = 25 } = {}, thunkAPI) => {
    try {
      const response = await api.get("/incidents", {
        params: { q, skip, limit },
      });
      return { items: response.data, q, skip, limit };
    } catch (error) {
      return thunkAPI.rejectWithValue(
        errorMessage(error, "Could not load incidents."),
      );
    }
  },
);

export const createIncident = createAsyncThunk(
  "incidents/createIncident",
  async (payload, thunkAPI) => {
    try {
      const response = await api.post("/incidents", payload);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        errorMessage(error, "Could not create incident."),
      );
    }
  },
);

export const updateIncident = createAsyncThunk(
  "incidents/updateIncident",
  async ({ id, payload }, thunkAPI) => {
    try {
      const response = await api.put(`/incidents/${id}`, payload);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        errorMessage(error, "Could not update incident."),
      );
    }
  },
);

export const deleteIncident = createAsyncThunk(
  "incidents/deleteIncident",
  async (id, thunkAPI) => {
    try {
      await api.delete(`/incidents/${id}`);
      return id;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        errorMessage(error, "Could not delete incident."),
      );
    }
  },
);

const initialState = {
  items: [],
  status: "idle",
  error: null,
  page: { q: "", skip: 0, limit: 25 },
};

const incidentsSlice = createSlice({
  name: "incidents",
  initialState,
  reducers: {
    clearIncidentError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchIncidents.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchIncidents.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload.items;
        state.page = {
          q: action.payload.q,
          skip: action.payload.skip,
          limit: action.payload.limit,
        };
      })
      .addCase(fetchIncidents.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload || "Could not load incidents.";
      })
      .addCase(createIncident.pending, (state) => {
        state.error = null;
      })
      .addCase(createIncident.fulfilled, (state, action) => {
        state.items.unshift(action.payload);
      })
      .addCase(createIncident.rejected, (state, action) => {
        state.error = action.payload || "Could not create incident.";
      })
      .addCase(updateIncident.fulfilled, (state, action) => {
        const index = state.items.findIndex(
          (item) => item.id === action.payload.id,
        );
        if (index !== -1) state.items[index] = action.payload;
      })
      .addCase(updateIncident.rejected, (state, action) => {
        state.error = action.payload || "Could not update incident.";
      })
      .addCase(deleteIncident.fulfilled, (state, action) => {
        state.items = state.items.filter((item) => item.id !== action.payload);
      })
      .addCase(deleteIncident.rejected, (state, action) => {
        state.error = action.payload || "Could not delete incident.";
      });
  },
});

export const { clearIncidentError } = incidentsSlice.actions;
export default incidentsSlice.reducer;
