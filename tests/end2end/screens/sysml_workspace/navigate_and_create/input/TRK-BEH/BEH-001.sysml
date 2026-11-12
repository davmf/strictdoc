package 'BEH-001' {
    private import StateMachineProfile::*;
    private import 'TRK-SYS'::*;

    // An item without a short name: its ID is its package name
    part kettle : StateMachine {
        :>> name = "Kettle";

        part :>> top : Region {
            part init : Pseudostate { :>> kind = PseudostateKind::initial; }
            part idle : State { :>> name = "Idle"; }
            part heating : CompositeState {
                :>> name = "Heating";
                part :>> regions : Region {
                    part start : Pseudostate { :>> kind = PseudostateKind::initial; }
                    part ramp : State { :>> name = "Ramp"; }
                    part hold : State { :>> name = "Hold"; }
                    connection startToRamp : Transition connect start.outgoing to ramp.incoming {
                        :>> classification = TransitionClassification::primary;
                    }
                    connection rampToHold : Transition connect ramp.outgoing to hold.incoming {
                        :>> classification = TransitionClassification::primary;
                    }
                }
            }
            connection initToIdle : Transition connect init.outgoing to idle.incoming {
                :>> classification = TransitionClassification::primary;
            }
            connection idleToHeating : Transition connect idle.outgoing to heating.incoming {
                :>> classification = TransitionClassification::primary;
            }
            connection heatingToIdle : Transition connect heating.outgoing to idle.incoming {
                :>> classification = TransitionClassification::secondary;
            }
            connection dryBoil : Transition connect heating.outgoing to idle.incoming {
                :>> classification = TransitionClassification::exception;
            }
        }
    }

    satisfy 'SYS-002' by kettle;
}
