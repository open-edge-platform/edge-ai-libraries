import { defineStore } from "pinia";

export const useLibraryStore = defineStore("library", {
  state: () => ({ selectedName: "" }),
  persist: {
    key: "consoleLibrary",
    storage: localStorage,
  },
});
