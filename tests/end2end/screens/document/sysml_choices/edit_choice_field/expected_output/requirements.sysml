package 'Requirements' {
    private import Choices::Tracker::*;

    requirement <'REQ-1'> 'First' {
        doc /*
         * First statement.
         */
        attribute status : Status = Status::'Waiting for approval';
    }
}
