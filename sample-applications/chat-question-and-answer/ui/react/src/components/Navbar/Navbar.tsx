import classes from "./Navbar.module.scss"
import { SYSTEM_INFO } from "../../config";

export function Navbar() {
    return (
        <header className={classes.navbar}>
            <div className={classes.navLeft}>
                <span className={classes.navTitle}>Chat QnA</span>
            </div>
            <div>
                <span className={classes.navTitle}>{SYSTEM_INFO}</span>
            </div>
        </header>
    )
}