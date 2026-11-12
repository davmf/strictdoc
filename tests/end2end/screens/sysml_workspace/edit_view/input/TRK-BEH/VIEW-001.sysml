package 'VIEW-001' {
    private import 'TRK-BEH'::*;

    view <'VIEW-001'> 'Heating only' {
        @StrictDocWorkspace::DiagramView {
            options = "transitions=primary";
            plantuml = "note right of ramp : reviewed\nnote right of hold : ok";
        }
        expose 'BEH-001'::top::heating::**;
    }
}
