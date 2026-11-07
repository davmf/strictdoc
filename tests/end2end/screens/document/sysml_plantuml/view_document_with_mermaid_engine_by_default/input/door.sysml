package DoorController {
  doc /* A door controller with two states, drawn by the StateMachineProfile. */

  private import StateMachineProfile::*;

  part doorSm : StateMachine {
    :>> name = "door";

    item :>> events {
      item openCmd  : Event { :>> name = "open"; }
      item closeCmd : Event { :>> name = "close"; }
    }

    part :>> top : Region {
      :>> name = "top";

      part init : Pseudostate {
        :>> name = "init";
        :>> kind = PseudostateKind::initial;
      }
      part closed : State { :>> name = "Closed"; }
      part opened : State { :>> name = "Open"; }

      connection initToClosed : Transition connect init.outgoing to closed.incoming {
        :>> name = "init -> Closed";
        :>> kind = TransitionKind::external;
      }
      connection closedToOpen : Transition connect closed.outgoing to opened.incoming {
        :>> name = "Closed -> Open";
        :>> trigger = doorSm.events.openCmd;
        :>> kind = TransitionKind::external;
      }
      connection openToClosed : Transition connect opened.outgoing to closed.incoming {
        :>> name = "Open -> Closed";
        :>> trigger = doorSm.events.closeCmd;
        :>> kind = TransitionKind::external;
      }
    }
  }
}
