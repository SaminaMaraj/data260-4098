import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import api from "../../api/axios";

export const fetchRoutes = createAsyncThunk(
  "routes/fetchRoutes",
  async (_, thunkAPI) => {
    try {
      const response = await api.get("/routes", {
        params: { skip: 0, limit: 200 },
      });
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(
        error.response?.data?.detail || "Could not load routes.",
      );
    }
  },
);

const routesSlice = createSlice({
  name: "routes",
  initialState: { items: [], status: "idle", error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchRoutes.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchRoutes.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchRoutes.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload || "Could not load routes.";
      });
  },
});

export default routesSlice.reducer;
