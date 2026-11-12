package 'TRK-SYS' {
    @StrictDocWorkspace::Tracker { title = "System requirements"; kind = "requirements"; prefix = "SYS"; }
    doc /*
     * Requirements of the kettle.
     */

    public import 'SYS-F-HEATING'::*;
    public import 'SYS-F-SAFETY'::*;
}
