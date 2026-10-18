mergeInto(LibraryManager.library, {
  TalonHostSession__deps: ["$stringToNewUTF8"],
  TalonHostSession: function () {
    return stringToNewUTF8(Module["kneuronSession"] || "");
  },
  TalonHostEvent: function (json) {
    window.dispatchEvent(new CustomEvent("kneuron:talon", { detail: JSON.parse(UTF8ToString(json)) }));
  }
});
