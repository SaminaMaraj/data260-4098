import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8498/api/hw4",
  withCredentials: true,
});

export default api;
