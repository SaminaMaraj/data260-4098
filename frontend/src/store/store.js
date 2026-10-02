import { configureStore } from "@reduxjs/toolkit";
import incidentsReducer from "../features/incidents/incidentsSlice";
import routesReducer from "../features/routes/routesSlice";

const store = configureStore({
  reducer: {
    incidents: incidentsReducer,
    routes: routesReducer,
  },
});

export default store;
